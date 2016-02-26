# Copyright 2015 Hewlett-Packard Corporation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import copy
import datetime
from elasticsearch import helpers
import fnmatch
import logging
import oslo_utils
import six

from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight import i18n


# Refer to ROLE_USER_FIELD
ADMIN_ID_SUFFIX = "_ADMIN"
USER_ID_SUFFIX = "_USER"

LOG = logging.getLogger(__name__)
_LW = i18n._LW
VERSION_CONFLICT_MSG = 'version_conflict_engine_exception'


def get_now_str():
    """Wrapping this to make testing easier (mocking utcnow's troublesome)
    and keep it in one place in case oslo changes
    """
    return oslo_utils.timeutils.isotime(datetime.datetime.utcnow())


def normalize_date_fields(document,
                          created_at='created',
                          updated_at='updated'):
    """Attempt to normalize documents to make it easier for consumers,
    particularly around sorting.
    """
    if created_at and 'created_at' not in document:
        document[u'created_at'] = document[created_at]
    if updated_at and 'updated_at' not in document:
        document[u'updated_at'] = document[updated_at]


def get_facets_query(fields, limit_terms):
    term_aggregations = {}
    for facet in fields:
        if isinstance(facet, tuple):
            facet_name, actual_field = facet
        else:
            facet_name, actual_field = facet, facet
        if '.' in facet_name:
            # Needs a nested aggregate
            term_aggregations[facet_name] = {
                "nested": {"path": facet_name.split('.')[0]},
                "aggs": {
                    # TODO(sjmc7): Handle deeper nesting?

                    facet_name: {
                        'terms': {
                            'field': actual_field,
                            'size': limit_terms
                        },
                        "aggs": {
                            facet_name + '__unique_docs': {
                                "reverse_nested": {}
                            }
                        }
                    }
                }
            }
        else:
            term_aggregations[facet_name] = {
                'terms': {'field': actual_field, 'size': limit_terms}
            }
    return term_aggregations


def transform_facets_results(result_aggregations, resource_type):
    """This effectively reverses the logic from `get_facets_query`,
    and produces output that looks the same regardless of whether
    a faceted field happens to be nested.

    The input should be the value of the `aggregations` keypair in the
    Elasticsearch response. Inputs can be of two forms:
      {"not_nested": {"buckets": [{"key": "something", "doc_count": 10}..]},
       "nested": "buckets": [
          {"key": 4, "doc_count": 2, "nested__unique_docs": {"doc_count": 1}},
          {"key": 6, "doc_count": 3, "nested__unique_docs": {"doc_count": 2}}
      ]}

    Output is normalized (using the __unique_docs count) to:
      {"not_nested": {"buckets": [{"key": "something", "doc_count": 10}..]},
       "nested": {"buckets": [
          {"key": 4, "doc_count": 1},
          {"key": 6, "doc_count": 2}
       ]}
    """
    facet_terms = {}
    for term, aggregation in six.iteritems(result_aggregations):
        if term in aggregation:
            # Again, deeper nesting question
            term_buckets = aggregation[term]['buckets']
            for bucket in term_buckets:
                reversed_agg = bucket.pop(term + "__unique_docs")
                bucket["doc_count"] = reversed_agg["doc_count"]
            facet_terms[term] = term_buckets
        elif 'buckets' in aggregation:
            facet_terms[term] = aggregation['buckets']
        else:
            # This can happen when there's no mapping defined at all..
            format_msg = {
                'field': term,
                'resource_type': resource_type
            }
            LOG.warning(_LW(
                "Unexpected aggregation structure for field "
                "'%(field)s' in %(resource_type)s. Is the mapping "
                "defined correctly?") % format_msg)
            facet_terms[term] = []
    return facet_terms


class IndexingHelper(object):
    """Class to abstract away some of the details of indexing documents
    including versioning, parent-child links and separation by role.

    Role separation is reasonably simple; documents with admin-only fields
    will be indexed twice, once for admins and once for normal users, with some
    fields excluded for the second case. The document IDs use the suffixes
    defined in ADMIN_ID_SUFFIX and USER_ID_SUFFIX.

    In the case of parent child relationships things are more complicated. The
    ids in that case follow these rules:
    * parent is role separated
      * child is role separated: the _USER and _ADMIN docs each refer to a
            parent with the same suffix
      * child is NOT separated: this case is not encouraged, but where it
            exists the child documents will use the _USER parent document as
            their _parent to avoid security issues with has_parent query
            fishing
    * parent is not role separated
      * child is role separated: both child docs will use the parent id
            without any prefix
      * child is not role separated: the simple case; no suffix in either
            case
    """
    def __init__(self, plugin):
        self.plugin = plugin

        # Retain some state here for convenience
        self.engine = self.plugin.engine
        self.index_name = plugin.index_name
        self.document_type = plugin.document_type

    @property
    def index_chunk_size(self):
        return 200

    def save_document(self, document, version=None):
        if version:
            self.save_documents([document], [version])
        else:
            self.save_documents([document])

    def save_documents(self, documents, versions=None):
        """Send list of serialized documents into search engine."""
        try:
            result = helpers.bulk(
                client=self.engine,
                index=self.index_name,
                doc_type=self.document_type,
                chunk_size=self.index_chunk_size,
                actions=self._apply_role_filtering(documents, versions))
        except helpers.BulkIndexError as e:
            err_msg = []
            for err in e.errors:
                if "VersionConflict" not in err['index']['error']:
                    raise e
                err_msg.append("id %(_id)s: %(error)s" % err['index'])
            LOG.warning(_LW('Version conflict %s') % ';'.join(err_msg))
            result = 0
        LOG.debug("Indexing result: %s", result)

    def delete_document(self, document):
        """'document' must contain an '_id', but can include '_parent' and
        '_version', each of which will be passed to the bulk helper
        """
        self.delete_documents([document])

    def delete_documents(self, metadocs, override_role_separation=False):
        """Each metadoc should be a dict with at an _id, and if
         applicable, a _parent. override_role_separation will treat the _ids
         and _parents in the documents as their actual indexed values
         rather than determining role separation
         """
        def _get_delete_action(doc, id_suffix=''):
            action = {'_op_type': 'delete', '_id': doc['_id'] + id_suffix}

            if doc.get('_version'):
                action['_version'] = doc['_version']
                action['_version_type'] = 'external'

            parent_entity_id = doc.get('_parent')
            if parent_entity_id:
                if (not override_role_separation and
                        self.plugin.parent_plugin.requires_role_separation):
                    # Default to _USER; defaulting to _ADMIN causes a
                    # security issue because of potential fishing queries
                    parent_entity_id += (id_suffix or USER_ID_SUFFIX)
                action['_parent'] = parent_entity_id
            return action

        actions = []
        for metadoc in metadocs:
            if (not override_role_separation and
                    self.plugin.requires_role_separation):
                actions.extend([
                    _get_delete_action(metadoc, ADMIN_ID_SUFFIX),
                    _get_delete_action(metadoc, USER_ID_SUFFIX)])
            else:
                actions.append(_get_delete_action(metadoc))

        try:
            helpers.bulk(
                client=self.plugin.engine,
                index=self.index_name,
                doc_type=self.document_type,
                actions=actions
            )
        except helpers.BulkIndexError as exc:
            exc_payload = exc[1]
            doc_ids = ', '.join(e['delete']['_id'] for e in exc_payload)

            if all(e['delete']['status'] == 404 for e in exc_payload):
                LOG.warning(
                    _LW("Error deleting %(doc_type)s %(ids)s; "
                        "already deleted") %
                    {"doc_type": self.plugin.document_type, "ids": doc_ids})

            elif all(e['delete']['status'] == 409 for e in exc_payload):
                # This *should* never happen. If it does, something has gone
                # wrong but leaving this here for now
                LOG.warning(
                    _LW("Error deleting %(doc_type)s %(ids)s; newer versions "
                        "of some documents have been indexed") %
                    {"doc_type": self.plugin.document_type, "ids": doc_ids})
            else:
                raise

    def delete_documents_with_parent(self, parent_id, version=None):
        # This is equivalent in result to _parent: parent_id but offers
        # a significant performance boost because of the implementation
        # of _parent filtering
        parent_type = self.plugin.parent_plugin_type()

        if (self.plugin.parent_plugin and
                self.plugin.parent_plugin.requires_role_separation):
            # There will be documents with the _USER suffix; there may also
            # be those with _ADMIN suffixes if this plugin type is separated
            full_parent_ids = [
                '%s#%s%s' % (parent_type, parent_id, ADMIN_ID_SUFFIX),
                '%s#%s%s' % (parent_type, parent_id, USER_ID_SUFFIX)
            ]
        else:
            full_parent_ids = '%s#%s' % (parent_type, parent_id)

        # It's easier to retrieve the actual parent id here because otherwise
        # we have to figure out role separation. _parent is (in 1.x) not
        # return by default and has to be requested in 'fields'
        query = {
            'fields': ['_parent'],
            'query': {
                'term': {
                    '_parent': full_parent_ids
                }
            }
        }

        documents = helpers.scan(
            client=self.engine,
            index=self.index_name,
            doc_type=self.document_type,
            query=query)

        to_delete = [{'_id': doc['_id'], '_parent': doc['fields']['_parent']}
                     for doc in documents]

        # Use the parent version tag; we're instructing elasticsearch to mark
        # all the deleted child documents as 'don't apply updates received
        # after 'version' so the fact that they don't match the child
        # 'updated_at' fields is irrelevant
        if version:
            for action in to_delete:
                action['_version'] = version

        self.delete_documents(to_delete, override_role_separation=True)

    def get_document(self, doc_id, for_admin=False):
        if self.plugin.requires_role_separation:
            doc_id += (ADMIN_ID_SUFFIX if for_admin else USER_ID_SUFFIX)

        return self.engine.get(
            index=self.index_name,
            doc_type=self.document_type,
            id=doc_id
        )

    def update_document(self, document, doc_id, update_as_script):
        """Updates are a little simpler than inserts because the documents
        already exist. Note that scripted updates are not filtered in the same
        way as partial document updates. Script updates should be passed as
        a dict {"script": .., "parameters": ..}. Partial document updates
        should be the raw document.
        """
        def _get_update_action(source, id_suffix=''):
            action = {'_id': doc_id + id_suffix, '_op_type': 'update'}
            if update_as_script:
                action.update(source)
            else:
                action['doc'] = source

            return action

        if self.plugin.requires_role_separation:
            user_doc = (self._remove_admin_fields(document)
                        if update_as_script else document)
            actions = [_get_update_action(document, ADMIN_ID_SUFFIX),
                       _get_update_action(user_doc, USER_ID_SUFFIX)]
        else:
            actions = [_get_update_action(document)]
        result = helpers.bulk(
            client=self.engine,
            index=self.index_name,
            doc_type=self.document_type,
            chunk_size=self.index_chunk_size,
            actions=actions)
        LOG.debug("Update result: %s", result)

    def _apply_role_filtering(self, documents, versions=None):
        """Returns a generator of indexable 'actions'. If the plugin requires
        role-based separation, two actions will be yielded per document,
        otherwise one. _id and USER_ROLE_FIELD are set as appropriate
        """
        def _get_index_action(source, version=None, id_suffix=''):
            """Return an 'action' the ES bulk indexer understands"""
            action = {
                '_id': source[self.plugin.get_document_id_field()] + id_suffix,
                '_source': source,
                '_op_type': 'index'
            }
            if version:
                action['_version_type'] = 'external'
                action['_version'] = version

            parent_field = self.plugin.get_parent_id_field()
            if parent_field:
                parent_id = source[parent_field]
                if self.plugin.parent_plugin.requires_role_separation:
                    # Default to _USER; defaulting to _ADMIN causes a
                    # security issue because of potential fishing queries
                    parent_id += (id_suffix or USER_ID_SUFFIX)
                action['_parent'] = parent_id
            return action

        for index, document in enumerate(documents):
            # Although elasticsearch copies the input when indexing, it's
            # easier from a debugging and testing perspective not to meddle
            # with the input, so make a copy
            document = copy.deepcopy(document)
            version = versions[index] if versions else None
            if self.plugin.requires_role_separation:
                LOG.debug("Applying role separation to %s id %s" %
                          (self.plugin.name,
                           document[self.plugin.get_document_id_field()]))
                document[ROLE_USER_FIELD] = 'admin'
                yield _get_index_action(document,
                                        version=version,
                                        id_suffix=ADMIN_ID_SUFFIX)

                user_doc = self._remove_admin_fields(document)
                user_doc[ROLE_USER_FIELD] = 'user'
                yield _get_index_action(user_doc,
                                        version=version,
                                        id_suffix=USER_ID_SUFFIX)

            else:
                LOG.debug("Not applying role separation to %s id %s" %
                          (self.plugin.name,
                           document[self.plugin.get_document_id_field()]))
                document[ROLE_USER_FIELD] = ['user', 'admin']
                yield _get_index_action(document, version=version)

    def _remove_admin_fields(self, document):
        """Prior to indexing, remove any fields that shouldn't be indexed
        and available to users who do not have administrative privileges.
        Returns a copy of the document even if there's nothing to remove.
        """
        sanitized_document = {}
        for k, v in six.iteritems(document):
            # Only return a field if it doesn't have ANY matches against
            # admin_only_fields
            if not any(fnmatch.fnmatch(k, field)
                       for field in self.plugin.admin_only_fields):
                sanitized_document[k] = v

        return sanitized_document
