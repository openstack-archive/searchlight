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
from elasticsearch import exceptions as es_exc
from elasticsearch import helpers
import fnmatch
import logging
import oslo_utils
import six


from oslo_utils import encodeutils
import searchlight.elasticsearch
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight import i18n

# Refer to ROLE_USER_FIELD
ADMIN_ID_SUFFIX = "_ADMIN"
USER_ID_SUFFIX = "_USER"

# Format for datetime when creating a unique index.
FORMAT = "%Y_%m_%d_%H_%M_%S"

# String from Alias Failure Exception. See _is_multiple_alias_exception().
ALIAS_EXCEPTION_STRING = "has more than one indices associated with it"

LOG = logging.getLogger(__name__)
_LW = i18n._LW
_LE = i18n._LE

VERSION_CONFLICT_MSG = 'version_conflict_engine_exception'

DOC_VALUE_TYPES = ('long', 'integer', 'short', 'boolean', 'byte',
                   'double', 'float', 'date', 'binary', 'geo_point', 'ip')


def get_now_str():
    """Wrapping this to make testing easier (mocking utcnow's troublesome)
    and keep it in one place in case oslo changes
    """
    return oslo_utils.timeutils.isotime(datetime.datetime.utcnow())


def timestamp_to_isotime(timestamp):
    """Take a rabbitmq-style timestamp (2016-03-14 16:49:23.749458) and convert
    to an ISO8601 timestamp.
    """
    fmt = '%Y-%m-%d %H:%M:%S.%f'
    parsed_time = datetime.datetime.strptime(timestamp, fmt)
    return oslo_utils.timeutils.isotime(parsed_time)


def helper_reindex(client, source_index, target_index, query=None,
                   target_client=None, chunk_size=500, scroll='5m',
                   scan_kwargs={}, bulk_kwargs={}):
    """We have lovingly copied the entire helpers.reindex function here:
           lib/python2.7/site-packages/elasticsearch/helpers/__init__.py.
       We need our own version (haha) of reindex to handle external versioning
       within a document. The current implmenentation of helpers.reindex does
       not provide this support. Since there is no way to tell helpers.bulk()
       that an external version is being used, we will need to modify each
       document in the generator. For future maintainablilty, modifications
       to the original method will be preceeded with a comment "CHANGED:".
       Minor tweaks made for PEP8 conformance excepted.
    """

    """
    Reindex all documents from one index that satisfy a given query
    to another, potentially (if `target_client` is specified) on a different
    cluster. If you don't specify the query you will reindex all the documents.

    .. note::

        This helper doesn't transfer mappings, just the data.

    :arg client: instance of :class:`~elasticsearch.Elasticsearch` to use (for
        read if `target_client` is specified as well)
    :arg source_index: index (or list of indices) to read documents from
    :arg target_index: name of the index in the target cluster to populate
    :arg query: body for the :meth:`~elasticsearch.Elasticsearch.search` api
    :arg target_client: optional, is specified will be used for writing (thus
        enabling reindex between clusters)
    :arg chunk_size: number of docs in one chunk sent to es (default: 500)
    :arg scroll: Specify how long a consistent view of the index should be
        maintained for scrolled search
    :arg scan_kwargs: additional kwargs to be passed to
        :func:`~elasticsearch.helpers.scan`
    :arg bulk_kwargs: additional kwargs to be passed to
        :func:`~elasticsearch.helpers.bulk`
    """
    target_client = client if target_client is None else target_client

    docs = helpers.scan(client, query=query, index=source_index,
                        scroll=scroll,
                        fields=('_source', '_parent', '_routing',
                                '_timestamp'), **scan_kwargs)

    def _change_doc_index(hits, index):
        for h in hits:
            h['_index'] = index
            # CHANGED: Allow for external versions to be indexed.
            h['_version_type'] = "external"
            if 'fields' in h:
                h.update(h.pop('fields'))
            yield h

    kwargs = {
        'stats_only': True,
    }
    kwargs.update(bulk_kwargs)
    return helpers.bulk(target_client, _change_doc_index(docs, target_index),
                        chunk_size=chunk_size, **kwargs)


def reindex(src_index, dst_index, type_list, chunk_size=None, time=None):
    """Reindex a set of indexes internally within ElasticSearch. All of the
       documents under the types that live in "type_list" under the index
       "src_index" will be copied into the documents under the same types
       in the index "dst_index". In other words, a perfect re-index!
       Instead of using the plugin API and consuming bandwidth to perform
       the re-index we will allow ElasticSearch to do some heavy lifting for
       us. Under the covers we are combining scan/scroll with bulk operations
       to do this re-indexing as efficient as possible.
    """
    es_engine = searchlight.elasticsearch.get_api()

    # Create a Query DSL string to access all documents within the specified
    # document types. We will filter on the "_type" field in this index. Since
    # there are multple docuent types, we will need to use the "terms" filter.
    # All of the document types will be added to the list for "_type". We need
    # to enable version to allow the search to return the version field. This
    # will be used by the reindexer.
    body = {"version": "true",
            "query": {"filtered": {"filter": {"terms": {"_type": type_list}}}}}
    # Debug: Show all documents that ES will re-index.
    # LOG.debug(es_engine.search(index=src_index, body=body, size=500))
    helper_reindex(client=es_engine, source_index=src_index,
                   target_index=dst_index, query=body)


def create_new_index(group):
    """Create a new index for a specific Resource Type Group. Upon
       exit of this method, the index is still not ready to be used.
       The index still needs to have the settings/mappings set for
       each plugin (Document Type).
    """
    es_engine = searchlight.elasticsearch.get_api()

    index_name = None
    while not index_name:
        # Use utcnow() to ensure that the name is unique.
        index_name = group + '-' + datetime.datetime.utcnow().strftime(FORMAT)
        try:
            es_engine.indices.create(index=index_name)
        except es_exc.ConflictError:
            # This index already exists! Try again.
            index_name = None

    return index_name


def setup_alias(index_name, alias_search, alias_listener):
    """Create all needed aliases. Each Resource Type Group will have two
       aliases. Each alias will point to the same internal index. As a
       reminder, all ES CRUD operations should go to the listener alias.
       All ES Query operations should go to the search alias.
    """
    es_engine = searchlight.elasticsearch.get_api()

    if not es_engine.indices.exists_alias(name=alias_search):
        # Search alias does not exist, create it and continue.
        try:
            es_engine.indices.put_alias(index=index_name,
                                        name=alias_search)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            es_engine.indices.delete(index=index_name)
            raise

    if not es_engine.indices.exists_alias(name=alias_listener):
        # Listener alias does not exist, create it and return.
        try:
            es_engine.indices.put_alias(index=index_name,
                                        name=alias_listener)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            es_engine.indices.delete(index=index_name)
            raise
        return

    # Listener alias exists, add the new index to it.
    body = {
        'actions': [
            {'add': {
                'index': index_name,
                'alias': alias_listener}}
        ]
    }
    try:
        es_engine.indices.update_aliases(body=body)
    except Exception as e:
        LOG.error(encodeutils.exception_to_unicode(e))
        es_engine.indices.delete(index=index_name, ignore=404)
        raise


def alias_search_update(alias_search, index_name):
    """Replace the current index with the specified index in the
       search alias. To avoid a race condition we will need to
       perform the remove and add atomically (within ElasticSearch).
    """
    if not index_name:
        return None

    es_engine = searchlight.elasticsearch.get_api()

    body = {
        'actions': [
            {'add': {
                'index': index_name,
                'alias': alias_search}}
        ]
    }
    try:
        current_indices = es_engine.indices.get_alias(
            name=alias_search, ignore=404)
        # Grab first (and only) index in the list from get_alias().
        old_index = current_indices.keys()[0]
        if old_index == index_name:
            return None
        body['actions'].insert(0,
                               {'remove': {
                                   'index': old_index,
                                   'alias': alias_search}})
    except Exception:
        # Alias doesn't exist. strange. Nothing to remove, only an add.
        pass

    try:
        es_engine.indices.update_aliases(body)
    except Exception as e:
        # The alias probably still refers to the index. Log the error and stop.
        # Continuing may result in the index being deleted and catastrophic
        # failure later.
        LOG.error(encodeutils.exception_to_unicode(e))
        raise

    return old_index


def alias_listener_update(alias_listener, index_name):
    """Delete the specified index from the listener alias. """

    if not index_name:
        return

    es_engine = searchlight.elasticsearch.get_api()

    body = {
        'actions': [
            {'remove': {
                'index': index_name,
                'alias': alias_listener}}
        ]
    }

    # If the index no longer exists, ignore and continue.
    try:
        es_engine.indices.update_aliases(body=body, ignore=404)
        es_engine.indices.delete(index=index_name, ignore=404)
    except Exception as e:
        # If the exception happens with the update, the alias may
        # still refer to the index. We do not want to delete the
        # index for this case. Log the error and continue.
        LOG.error(encodeutils.exception_to_unicode(e))


def alias_error_cleanup(indexes):
    """While trying to re-index, we ran into some error. In this case, the
       new index creation/alias updating is incorrect. We will need to clean
       up by rolling back all of the changes. ElasticSearch must stay
       uncluttered. We will delete the indexes explicitly here. ElasticSearch
       will implicitly take care of removing deleted indexes from the aliases.
    """

    es_engine = searchlight.elasticsearch.get_api()

    for index in indexes.values():
        try:
            es_engine.indices.delete(index=index, ignore=404)
        except Exception as e:
            msg = {'index': index}
            LOG.error(_LE("Index [%(index)s] clean-up failed.") % msg)
            LOG.error(encodeutils.exception_to_unicode(e))


def _is_multiple_alias_exception(e):
    """Verify that this exception is specifically the IllegalArgument
       exception when there are multiple indexes for an alias. There
       is no clean way of verifying this is the case. There are multiple
       ES RequestError exceptions that return a 400 IllegalArgument.
       In this particular case, we are expecting a message in the
       exception like this:

           ElasticsearchIllegalArgumentException[Alias [alias] has more
           than one indices associated with it [[idx1, idx2]], can't
           execute a single index op]

       We will be dirty and parse the exception message. We need to
       check the validity of ALIAS_EXCPTION_STRING in future
       ElasticSearch versions.
    """
    if ALIAS_EXCEPTION_STRING in getattr(e, 'error', ''):
        return True
    else:
        return False


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
        self.alias_name = plugin.alias_name_listener
        self.document_type = plugin.document_type

    @property
    def index_chunk_size(self):
        return 200

    def _index_alias_multiple_indexes_bulk(self, documents=None, actions=None,
                                           versions=None):
        """A bulk operation failed by trying to access an alias that has
           multiple indexes. To rememdy this we will need to iterate on all
           indexes within the alias and retry the bulk operation individually.
        """
        indexes = self.engine.indices.get_alias(index=self.alias_name)
        for index_name in indexes:
            try:
                if documents:
                    result = helpers.bulk(
                        client=self.engine,
                        index=index_name,
                        doc_type=self.document_type,
                        chunk_size=self.index_chunk_size,
                        actions=self._prepare_actions(documents,
                                                      versions))
                if actions:
                    result = helpers.bulk(
                        client=self.engine,
                        index=index_name,
                        doc_type=self.document_type,
                        chunk_size=self.index_chunk_size,
                        actions=actions)
                LOG.debug("Indexing result: %s", result)
            except Exception as e:
                # Log the error and continue to the next index.
                format_msg = {
                    'doc': self.document_type,
                    'msg': str(e)
                }
                LOG.error(_LE("Failed Indexing %(doc)s: %(msg)s") % format_msg)

    def _index_alias_multiple_indexes_get(self, doc_id, routing=None):
        """Getting a document from an alias with multiple indexes will fail.
           We need to retrive it from one of the indexes. We will choose
           the latest index. Since the indexes are named with a timestamp,
           a reverse sort will bring the latest to the front.
        """
        indexes = self.engine.indices.get_alias(index=self.alias_name)
        index_list = indexes.keys()
        index_list.sort(reverse=True)
        try:
            if routing:
                return self.engine.get(
                    index=index_list[0],
                    doc_type=self.document_type,
                    id=doc_id,
                    routing=routing
                )
            else:
                return self.engine.get(
                    index=index_list[0],
                    doc_type=self.document_type,
                    id=doc_id
                )
        except Exception as e:
            format_msg = {
                'doc': self.document_type,
                'msg': str(e)
            }
            LOG.error(_LE("Failed Indexing %(doc)s: %(msg)s") % format_msg)

    def save_document(self, document, version=None):
        if version:
            self.save_documents([document], [version])
        else:
            self.save_documents([document])

    def save_documents(self, documents, versions=None, index=None):
        """Send list of serialized documents into search engine."""

        """Warning: Index vs Alias usage.
           Listeners [plugins/*/notification_handlers.py]:
           When the plugin listeners are indexing documents, we will want
           to use the normal ES alias for their resource group. In this case
           the index parameter will not be set. Listeners are by far the most
           common usage case.

           Re-Indexing [plugins/base.py::initial_indexing()]:
           When we are re-indexing we will want to use the new ES index.
           Bypassing the alias means we will not send duplicate documents
           to the old index. In this case the index will be set. Re-indexing
           is an event that will rarely happen.
        """
        if not index:
            use_index = self.alias_name
        else:
            use_index = index

        try:
            result = helpers.bulk(
                client=self.engine,
                index=use_index,
                doc_type=self.document_type,
                chunk_size=self.index_chunk_size,
                actions=self._prepare_actions(documents, versions))
        except helpers.BulkIndexError as e:
            err_msg = []
            for err in e.errors:
                if "VersionConflict" not in err['index']['error']:
                    raise e
                err_msg.append("id %(_id)s: %(error)s" % err['index'])
            LOG.warning(_LW('Version conflict %s') % ';'.join(err_msg))
            result = 0
        except es_exc.RequestError as e:
            if _is_multiple_alias_exception(e):
                LOG.error(_LE("Alias [%(a)s] with multiple indexes error") %
                          {'a': self.alias_name})
                self._index_alias_multiple_indexes_bulk(documents=documents,
                                                        versions=versions)

            result = 0
        LOG.debug("Indexing result: %s", result)

    def delete_document(self, document):
        """'document' must contain an '_id', but can include '_parent',
        '_version' and '_routing', each of which will be passed to
        the bulk helper
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
            if '_routing' in doc:
                action['_routing'] = doc['_routing']
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
                index=self.alias_name,
                doc_type=self.document_type,
                actions=actions
            )
        except helpers.BulkIndexError as exc:
            exc_payload = exc.errors
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
        except es_exc.RequestError as e:
            if _is_multiple_alias_exception(e):
                LOG.error(_LE("Alias [%(a)s] with multiple indexes error") %
                          {'a': self.alias_name})
                self._index_alias_multiple_indexes_bulk(actions=actions)

    def delete_documents_with_parent(self, parent_id, version=None):
        # This is equivalent in result to _parent: parent_id but offers
        # a significant performance boost because of the implementation
        # of _parent filtering
        parent_type = self.plugin.parent_plugin_type()

        # It's easier to retrieve the actual parent id here because otherwise
        # we have to figure out role separation. _parent is (in 1.x) not
        # return by default and has to be requested in 'fields'
        query = {
            'fields': ['_parent', '_routing']
        }

        if (self.plugin.parent_plugin and
                self.plugin.parent_plugin.requires_role_separation):
            # There will be documents with the _USER suffix; there may also
            # be those with _ADMIN suffixes if this plugin type is separated
            full_parent_ids = [
                '%s#%s%s' % (parent_type, parent_id, ADMIN_ID_SUFFIX),
                '%s#%s%s' % (parent_type, parent_id, USER_ID_SUFFIX)
            ]
            query['query'] = {'terms': {'_parent': full_parent_ids}}
        else:
            full_parent_id = '%s#%s' % (parent_type, parent_id)
            query['query'] = {'term': {'_parent': full_parent_id}}

        documents = helpers.scan(
            client=self.engine,
            index=self.alias_name,
            doc_type=self.document_type,
            query=query)

        to_delete = [
            {'_id': doc['_id'], '_parent': doc['fields']['_parent'],
             '_routing': doc['fields']['_routing']}
            if '_routing' in doc['fields']
            else {'_id': doc['_id'], '_parent': doc['fields']['_parent']}
            for doc in documents]

        # Use the parent version tag; we're instructing elasticsearch to mark
        # all the deleted child documents as 'don't apply updates received
        # after 'version' so the fact that they don't match the child
        # 'updated_at' fields is irrelevant
        if version:
            for action in to_delete:
                action['_version'] = version

        self.delete_documents(to_delete, override_role_separation=True)

    def get_document(self, doc_id, for_admin=False, routing=None):
        if self.plugin.requires_role_separation:
            doc_id += (ADMIN_ID_SUFFIX if for_admin else USER_ID_SUFFIX)

        try:
            if routing:
                return self.engine.get(
                    index=self.alias_name,
                    doc_type=self.document_type,
                    id=doc_id,
                    routing=routing
                )
            else:
                return self.engine.get(
                    index=self.alias_name,
                    doc_type=self.document_type,
                    id=doc_id
                )
        except es_exc.RequestError:
            # TODO(ricka) Verify this is the IllegalArgument exception.
            LOG.error(_LE("Alias [%(alias)s] with multiple indexes error") %
                      {'alias': self.alias_name})
            #
            return self._index_alias_multiple_indexes_get(
                doc_id=doc_id, routing=routing)

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

            routing_field = self.plugin.routing_field
            if routing_field:
                action['_routing'] = source[routing_field]

            return action

        if self.plugin.requires_role_separation:
            user_doc = (self._remove_admin_fields(document)
                        if update_as_script else document)
            actions = [_get_update_action(document, ADMIN_ID_SUFFIX),
                       _get_update_action(user_doc, USER_ID_SUFFIX)]
        else:
            actions = [_get_update_action(document)]
        try:
            result = helpers.bulk(
                client=self.engine,
                index=self.alias_name,
                doc_type=self.document_type,
                chunk_size=self.index_chunk_size,
                actions=actions)
            LOG.debug("Update result: %s", result)
        except es_exc.RequestError as e:
            if _is_multiple_alias_exception(e):
                LOG.error(_LE("Alias [%(a)s] with multiple indexes error") %
                          {'a': self.alias_name})
                self._index_alias_multiple_indexes_bulk(actions=actions)

    def _prepare_actions(self, documents, versions=None):
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
            routing_field = self.plugin.routing_field
            if parent_field:
                parent_id = source[parent_field]
                if self.plugin.parent_plugin.requires_role_separation:
                    # Default to _USER; defaulting to _ADMIN causes a
                    # security issue because of potential fishing queries
                    parent_id += (id_suffix or USER_ID_SUFFIX)
                action['_parent'] = parent_id
            if routing_field:
                action['_routing'] = source[routing_field]
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

    @classmethod
    def apply_doc_values(cls, mapping):
        """Sets 'doc_values' on fields in a mapping which allows queries to be
        run on fields directly off disk, saving memory in analysis operations.
        Currently all fields with the exception of analyzed strings can be set
        as doc_values. Elasticsearch 2.x will make doc_values the default.
        """
        def apply_doc_values(field_def):
            if field_def.get('type', 'object') in ('nested', 'object'):
                for _, nested_def in six.iteritems(field_def['properties']):
                    apply_doc_values(nested_def)
            else:
                if 'doc_values' not in field_def:
                    if field_def['type'] in DOC_VALUE_TYPES:
                        field_def['doc_values'] = True
                    elif (field_def['type'] == 'string' and
                          field_def.get('index', '') == 'not_analyzed'):
                        field_def['doc_values'] = True

                for _, multidef in six.iteritems(field_def.get('fields', {})):
                    apply_doc_values(multidef)

        # Check dynamic templates. These are a list of dicts each with a single
        # key (the template name) and a mapping definition
        for dynamic_template in mapping.get('dynamic_templates', []):
            for dyn_field, dyn_mapping in six.iteritems(dynamic_template):
                apply_doc_values(dyn_mapping['mapping'])

        for field, definition in six.iteritems(mapping['properties']):
            apply_doc_values(definition)
