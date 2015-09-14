# Copyright 2015 Intel Corporation
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

import abc
from elasticsearch import helpers
import logging
from oslo_config import cfg
from oslo_config import types
import six

import searchlight.elasticsearch
from searchlight import i18n
from searchlight import plugin


LOG = logging.getLogger(__name__)
_LW = i18n._LW


indexer_opts = [
    cfg.StrOpt('index_name', default="searchlight")
]

CONF = cfg.CONF
CONF.register_opts(indexer_opts, group='resource_plugin')


@six.add_metaclass(abc.ABCMeta)
class IndexBase(plugin.Plugin):
    chunk_size = 200

    def __init__(self):
        self.options = cfg.CONF[self.get_config_group_name()]

        self.engine = searchlight.elasticsearch.get_api()
        self.index_name = self.get_index_name()
        self.document_type = self.get_document_type()
        self.document_id_field = self.get_document_id_field()

        self.name = "%s-%s" % (self.index_name, self.document_type)

    def initial_indexing(self, clear=True):
        """Comprehensively install search engine index and put data into it."""
        self.check_mapping_sort_fields()

        if clear:
            # First delete the doc type
            self.clear_data()

        self.setup_index()
        self.setup_mapping()
        self.setup_data()

    def clear_data(self):
        type_exists = (self.engine.indices.exists(self.index_name) and
                       self.engine.indices.exists_type(self.index_name,
                                                       self.document_type))
        if type_exists:
            self.engine.indices.delete_mapping(self.index_name,
                                               self.document_type)

    def setup_index(self):
        """Create the index if it doesn't exist and update its settings."""
        index_exists = self.engine.indices.exists(self.index_name)
        if not index_exists:
            self.engine.indices.create(index=self.index_name)

        index_settings = self.get_settings()
        if index_settings:
            self.engine.indices.put_settings(index=self.index_name,
                                             body=index_settings)

        return index_exists

    def setup_mapping(self):
        """Update index document mapping."""
        index_mapping = self.get_mapping()

        if index_mapping:
            self.engine.indices.put_mapping(index=self.index_name,
                                            doc_type=self.document_type,
                                            body=index_mapping)

    def setup_data(self):
        """Insert all objects from database into search engine."""
        object_list = self.get_objects()
        documents = []
        for obj in object_list:
            document = self.serialize(obj)
            documents.append(document)

        self.save_documents(documents)

    def save_documents(self, documents):
        """Send list of serialized documents into search engine."""
        actions = []
        for document in documents:
            parent_field = self.get_parent_id_field()
            action = {
                '_id': document.get(self.document_id_field),
                '_source': document,
            }
            if parent_field:
                action['_parent'] = document[parent_field]

            actions.append(action)

        helpers.bulk(
            client=self.engine,
            index=self.index_name,
            doc_type=self.document_type,
            chunk_size=self.chunk_size,
            actions=actions)

    def get_facets(self, request_context, all_projects=False, limit_terms=0):
        """Get facets available for searching, in the form of a list of
        dicts with keys "name", "type" and optionally "options" if a field
        should have discreet allowed values
        """
        facets = []
        exclude_facets = self.facets_excluded
        is_admin = request_context.is_admin

        def include_facet(name):
            if name not in exclude_facets:
                return True

            if is_admin and exclude_facets[name]:
                return True

            return False

        def get_facets_for(mapping, prefix=''):
            facets = []
            for name, properties in six.iteritems(mapping):
                if properties.get('type') == 'nested':
                    if include_facet(prefix + name):
                        facets.extend(get_facets_for(properties['properties'],
                                                     "%s%s." % (prefix, name)))
                else:
                    if include_facet(name):
                        facets.append({
                            'name': prefix + name,
                            'type': properties['type']
                        })
            return facets

        facets = get_facets_for(self.get_mapping()['properties'])

        # Don't retrieve facet terms for any excluded fields
        included_fields = set(f['name'] for f in facets)
        facet_terms_for = set(self.facets_with_options) & included_fields
        facet_terms = self._get_facet_terms(facet_terms_for,
                                            request_context,
                                            all_projects,
                                            limit_terms)
        for facet in facets:
            if facet['name'] in facet_terms:
                facet['options'] = facet_terms[facet['name']]

        return facets

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options.
        """
        return {}

    @property
    def facets_with_options(self):
        """An iterable of facet names that support facet options"""
        return ()

    def _get_facet_terms(self, fields, request_context,
                         all_projects, limit_terms):
        term_aggregations = {}
        for facet in fields:
            if isinstance(facet, tuple):
                facet_name, actual_field = facet
            else:
                facet_name, actual_field = facet, facet
            if '.' in facet_name:
                # Needs a nested aggregate
                term_aggregations[facet_name.replace('.', '__')] = {
                    "nested": {"path": facet_name.split('.')[0]},
                    "aggs": {
                        # TODO(sjmc7): Handle deeper nesting?
                        facet_name.replace('.', '__'): {
                            'terms': {
                                'field': actual_field,
                                'size': limit_terms
                            },
                        }
                    }
                }
            else:
                term_aggregations[facet_name] = {
                    'terms': {'field': actual_field, 'size': limit_terms}
                }
        if term_aggregations:
            body = {
                'aggs': term_aggregations,
            }
            if not (request_context.is_admin and all_projects):
                plugin_filters = self._get_rbac_field_filters(request_context)
                if plugin_filters:
                    body['query'] = {
                        "filtered": {
                            "filter":
                                {"and": plugin_filters}
                        }}

            results = self.engine.search(
                index=self.get_index_name(),
                doc_type=self.get_document_type(),
                body=body,
                ignore_unavailable=True,
                search_type='count')

            facet_terms = {}
            result_aggregations = results.get('aggregations', {})
            for term, aggregation in six.iteritems(result_aggregations):
                if term in aggregation:
                    # Again, deeper nesting question
                    term_name = term.replace('__', '.')
                    facet_terms[term_name] = aggregation[term]['buckets']
                elif 'buckets' in aggregation:
                    facet_terms[term] = aggregation['buckets']
                else:
                    # This can happen when there's no mapping defined at all..
                    format_msg = {
                        'field': term,
                        'resource_type': self.get_document_type()
                    }
                    LOG.warning(_LW(
                        "Unexpected aggregation structure for field "
                        "'%(field)s' in %(resource_type)s. Is the mapping "
                        "defined correctly?") % format_msg)
                    facet_terms[term] = []

            if not result_aggregations:
                LOG.warning(_LW(
                    "No aggregations found for %(resource_type)s. There may "
                    "be a mapping problem.") %
                    {'resource_type': self.get_document_type()})
            return facet_terms
        return {}

    def check_mapping_sort_fields(self):
        """Check that fields that are expected to define a 'raw' field so so"""
        fields_needing_raw = searchlight.elasticsearch.RAW_SORT_FIELDS
        mapped_properties = self.get_mapping().get('properties', {})
        for field_name, field_mapping in six.iteritems(mapped_properties):
            if field_name in fields_needing_raw:
                raw = field_mapping.get('fields', {}).get('raw', None)
                if not raw:
                    msg_vals = {"field_name": field_name,
                                "index_name": self.get_index_name(),
                                "document_type": self.get_document_type()}
                    message = ("Field '%(field_name)s' for %(index_name)s/"
                               "%(document_type)s must contain a subfield "
                               "whose name is 'raw' for sorting." % msg_vals)
                    raise Exception(message)

    @abc.abstractmethod
    def get_objects(self):
        """Get list of all objects which will be indexed into search engine."""

    @abc.abstractmethod
    def serialize(self, obj):
        """Serialize database object into valid search engine document."""

    def get_document_id_field(self):
        """Whatever document field should be treated as the id. This field
        should also be mapped to _id in the elasticsearch mapping
        """
        return "id"

    def get_parent_id_field(self):
        """Whatever field should be treated as the parent id. This is required
        for plugins with _parent definitions in their mappings. Documents to be
        indexed should contain this field.
        """
        return None

    def get_index_name(self):
        if self.options.index_name is not None:
            return self.options.index_name
        else:
            return cfg.CONF.resource_plugin.index_name

    @property
    def enabled(self):
        return self.options.enabled

    @classmethod
    def get_document_type(cls):
        """Get name of the document type.

        This is in the format of OS::Service::Resource typically.
        """
        raise NotImplemented()

    def get_rbac_filter(self, request_context):
        """Get rbac filter as es json filter dsl. for non-admin queries."""
        # Add a document type filter to the plugin-specific fields
        plugin_filters = self._get_rbac_field_filters(request_context)
        document_type_filter = [{'type': {'value': self.get_document_type()}}]
        filter_fields = plugin_filters + document_type_filter

        return [
            {
                'indices': {
                    'index': self.get_index_name(),
                    'no_match_filter': 'none',
                    'filter': {
                        "and": filter_fields
                    }
                }
            }
        ]

    @abc.abstractmethod
    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """

    def filter_result(self, hit, request_context):
        """Filter each outgoing search result; document in hit['_source']"""
        pass

    def get_settings(self):
        """Get an index settings."""
        return {}

    def get_mapping(self):
        """Get an index mapping."""
        return {}

    def get_notification_handler(self):
        """Get the notification handler which implements NotificationBase."""
        return None

    def get_notification_supported_events(self):
        """Get the list of suppported event types."""
        return []

    @classmethod
    def get_topic_exchanges(cls):
        return []

    def get_notification_topics_exchanges(self):
        """"
        Get the set of topics and exchanges. This is to retain the old
        pattern without changing too much for now.
        """
        return [tuple(i.split(',')) for i in self.options.topic_exchanges]

    @classmethod
    def get_plugin_type(cls):
        return "resource_plugin"

    @classmethod
    def get_plugin_name(cls):
        return cls.get_document_type().replace("::", "_").lower()

    @classmethod
    def get_plugin_opts(cls):
        opts = [
            cfg.StrOpt("index_name"),
            cfg.BoolOpt("enabled", default=True)
        ]
        # TODO(sjmc7): Make this more flexible
        topic_exchanges = ["searchlight_indexer,%s" % i for i in
                           cls.get_notification_exchanges()]
        if topic_exchanges:
            opts.append(cfg.MultiOpt(
                'topic_exchanges',
                item_type=types.MultiString(),
                default=topic_exchanges))
        return opts

    @classmethod
    def get_config_group_name(cls):
        """Override the get_plugin_name in order to use the document type as
        plugin name. This turns OS::Service::Resource to os_service_resource
        """
        config_name = cls.get_document_type().replace("::", "_").lower()
        return "resource_plugin:%s" % config_name


@six.add_metaclass(abc.ABCMeta)
class NotificationBase(object):

    def __init__(self, engine, index_name, document_type):
        self.engine = engine
        self.index_name = index_name
        self.document_type = document_type

    @abc.abstractmethod
    def process(self, ctxt, publisher_id, event_type, payload, metadata):
        """Process the incoming notification message."""
