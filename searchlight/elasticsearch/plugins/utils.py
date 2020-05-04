# Copyright (c) 2015-2016 Hewlett-Packard Enterprise Development Company, L.P.
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

import datetime
from elasticsearch import exceptions as es_exc
from elasticsearch import helpers
import logging
import oslo_utils

from oslo_config import cfg
from oslo_utils import encodeutils

from searchlight.common import exception as sl_exc
from searchlight.common import utils
from searchlight.context import RequestContext
import searchlight.elasticsearch


# Format for datetime when creating a unique index.
FORMAT = "%Y_%m_%d_%H_%M_%S"

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

VERSION_CONFLICT_MSG = 'version_conflict_engine_exception'


def get_now_str():
    """Wrapping this to make testing easier (mocking utcnow's troublesome)
    and keep it in one place in case oslo changes
    """
    return utils.isotime(oslo_utils.timeutils.utcnow())


def timestamp_to_isotime(timestamp):
    """Take a rabbitmq-style timestamp (2016-03-14 16:49:23.749458) and convert
    to an ISO8601 timestamp.
    """
    fmt = '%Y-%m-%d %H:%M:%S.%f'
    parsed_time = datetime.datetime.strptime(timestamp, fmt)
    return utils.isotime(parsed_time)


def helper_reindex(client, source_index, target_index, query=None,
                   target_client=None, chunk_size=500, scroll='5m',
                   scan_kwargs={}, bulk_kwargs={}):
    """We have lovingly copied the entire helpers.reindex() method from the
       elasticsearch Python client. The original version lives here:
           https://github.com/elastic/elasticsearch-py
       In the file:
           elasticsearch/helpers/__init__.py
       This file is licensed under the Apache License.

       We need our own version (haha) of reindex to handle external versioning
       within a document. The current implmenentation of helpers.reindex does
       not provide this support. Since there is no way to tell helpers.bulk()
       that an external version is being used, we will need to modify each
       document in the generator. For future maintainablilty, modifications
       to the original method will be preceded with a comment "CHANGED:".
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
    # there are multiple docuent types, we will need to use the "terms" filter.
    # All of the document types will be added to the list for "_type". We need
    # to enable version to allow the search to return the version field. This
    # will be used by the reindexer.
    body = {"version": "true",
            "query": {"bool": {"filter": {"terms": {"_type": type_list}}}}}
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

    kwargs = {}
    index_settings = _get_index_settings_from_config()
    if index_settings:
        kwargs = {'body': {'index': index_settings}}

    index_name = None
    while not index_name:
        # Use utcnow() to ensure that the name is unique.
        now = oslo_utils.timeutils.utcnow()
        index_name = (group + '-' + now.strftime(FORMAT))
        try:
            es_engine.indices.create(index=index_name, **kwargs)
        except es_exc.TransportError as e:
            if (e.error.startswith("IndexAlreadyExistsException") or
                    e.error.startswith("index_already_exists_exception")):
                # This index already exists! Try again.
                index_name = None
            else:
                raise

    return index_name


def _get_index_settings_from_config():
    index_settings = {}
    if CONF.elasticsearch.index_gc_deletes is not None:
        index_settings['gc_deletes'] = CONF.elasticsearch.index_gc_deletes

    for setting, value in CONF.elasticsearch.index_settings.items():
        if setting.startswith('index.'):
            setting = setting[len('index_'):]

        index_settings[setting] = value

    return index_settings


def add_extra_mappings(index_name, doc_type_info):
    """Add mappings for the specified doc_types if they already do not
       exist in the index. This is to work around a "feature" in Elasticsearch.
       Specifying a doc_type in a query that spans multiple indices will fail
       if that doc_type is not present in all indices being queried. This type
       of query is used in Searchlight for the Resource Types that have a
       parent-child relationship (due to our RBAC model).
       The parameter doc_type_info is a list of tuples. Each entry contains
       a document type and whether this document type has a parent-child
       relationship.
    """
    es_engine = searchlight.elasticsearch.get_api()

    # Create an empty mapping that cannot be used. We need to make sure it
    # has a "_parent" field for the "has_parent" queries. Make sure that the
    # "_parent" field is not used anywhere else.
    for doc_type, has_parent in doc_type_info:
        body = {'dynamic': 'strict',
                'properties': {
                }}
        if has_parent:
            body['_parent'] = {'type': 'never_used_parent'}
        if not es_engine.indices.exists_type(index=index_name,
                                             doc_type=doc_type):
            es_engine.indices.put_mapping(index=index_name, doc_type=doc_type,
                                          body=body)


def get_index_refresh_interval(index_name):
    """Get the refresh_interval of a given index, if refresh_interval isn't
       set, return default 1s.
    """

    es_engine = searchlight.elasticsearch.get_api()
    try:
        result = es_engine.indices.get_settings(index_name,
                                                'index.refresh_interval')
    except Exception as e:
        # If we cannot get index setting, something must be wrong,
        # no need to continue, log the error message and raise.
        LOG.error(encodeutils.exception_to_unicode(e))
        raise

    if result:
        return result[index_name]['settings']['index']['refresh_interval']
    else:
        return '1s'


def set_index_refresh_interval(index_name, refresh_interval):
    """Set refresh_interval of a given index, basically it is used in the
       reindexing phase. By setting refresh_interval to -1 we disable the
       refresh of offline index to gain a performance boost for the bulk
       updates. After reindexing is done, we will restore refresh_interval
       and put the index online.
    """

    es_engine = searchlight.elasticsearch.get_api()

    body = {
        'index': {
            'refresh_interval': refresh_interval
        }
    }

    try:
        es_engine.indices.put_settings(body, index_name)
    except Exception as e:
        LOG.error(encodeutils.exception_to_unicode(e))
        raise


def refresh_index(index_name):
    """Do a refresh on a given index"""

    es_engine = searchlight.elasticsearch.get_api()

    try:
        es_engine.indices.refresh(index_name)
    except Exception as e:
        LOG.error(encodeutils.exception_to_unicode(e))
        raise


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
       perform the remove and add automatically (within ElasticSearch).
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
    old_index = None
    try:
        current_indices = es_engine.indices.get_alias(name=alias_search)
        # Grab first (and only) index in the list from get_alias().
        old_index = list(current_indices.keys())[0]
        if old_index == index_name:
            return None
        body['actions'].insert(0,
                               {'remove': {
                                   'index': old_index,
                                   'alias': alias_search}})

    except es_exc.NotFoundError:
        # Alias doesn't exist. Strange. Nothing to remove, only an add.
        old_index = None

    try:
        es_engine.indices.update_aliases(body)
    except Exception as e:
        # The alias probably still refers to the index. Log the error and stop.
        # Continuing may result in the index being deleted and catastrophic
        # failure later.
        LOG.error(encodeutils.exception_to_unicode(e))
        raise

    return old_index


def delete_index(index_name):
    """Delete the specified index. """

    if index_name is None:
        return
    # Alias will be cleaned up automatically by ES when the index is deleted.
    es_engine = searchlight.elasticsearch.get_api()
    es_engine.indices.delete(index=index_name, ignore=404)


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
            LOG.error("Index [%(index)s] clean-up failed." % msg)
            LOG.error(encodeutils.exception_to_unicode(e))


def get_indices(alias):
    """Return a list of indices associated with the specified alias.
    """
    es_engine = searchlight.elasticsearch.get_api()

    return es_engine.indices.get_alias(name=alias)


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


def get_facets_query(fields, nested_fields, limit_terms):
    term_aggregations = {}
    for facet in fields:
        if isinstance(facet, tuple):
            facet_name, actual_field = facet
        else:
            facet_name, actual_field = facet, facet
        if '.' in facet_name and facet_name.split('.')[0] in nested_fields:
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
    for term, aggregation in result_aggregations.items():
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
            LOG.warning(
                "Unexpected aggregation structure for field "
                "'%(field)s' in %(resource_type)s. Is the mapping "
                "defined correctly?" % format_msg)
            facet_terms[term] = []
    return facet_terms


def find_missing_types(index_type_mapping):
    """Find if doc types are not exist in given indices"""
    missing_index, missing_type = [], []

    if not index_type_mapping:
        return missing_index, missing_type

    es_engine = searchlight.elasticsearch.get_api()

    for index in index_type_mapping.keys():
        for doc_type in index_type_mapping[index]:
            try:
                mapping = es_engine.indices.get_mapping(index, doc_type)
                if not mapping:
                    missing_type.append(doc_type)
            except es_exc.NotFoundError:
                missing_index.append(index)

    return set(missing_index), set(missing_type)


def normalize_es_document(es_doc, plugin):
    """
    Remove any elasticsearch specific field and apply plugin's filter_result
    method to given document.
    """
    # Remove user role field
    es_doc.pop(searchlight.elasticsearch.ROLE_USER_FIELD, None)

    # Apply plugin's filter_result
    admin_context = RequestContext()
    plugin.filter_result({'_source': es_doc}, admin_context)
    return es_doc


def check_notification_version(expected, actual, notification_type):
    """
    If actual's major version is different from expected, a
    VersionedNotificationMismatch error is raised.
    If the minor versions are different, a DEBUG level log
    message is output
    """
    maj_ver, min_ver = map(int, actual.split('.'))
    expected_maj, expected_min = map(int, expected.split('.'))
    if maj_ver != expected_maj:
        raise sl_exc.VersionedNotificationMismatch(
            provided_maj=maj_ver, provided_min=min_ver,
            expected_maj=expected_maj, expected_min=expected_min,
            type=notification_type)

    if min_ver != expected_min:
        LOG.debug(
            "Notification minor version mismatch. "
            "Provided: %(provided_maj)s, %(provided_min)s. "
            "Expected: %(expected_maj)s.%(expected_min)s." % {
                "provided_maj": maj_ver, "provided_min": min_ver,
                "expected_maj": expected_maj, "expected_min": expected_min}
        )
