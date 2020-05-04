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
import calendar
import logging
from oslo_config import cfg
from oslo_config import types
from oslo_utils import encodeutils
from oslo_utils import timeutils
import re

from searchlight.common import exception
import searchlight.elasticsearch
from searchlight.elasticsearch.plugins import helper
from searchlight.elasticsearch.plugins import utils
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.i18n import _
from searchlight import plugin


LOG = logging.getLogger(__name__)

resource_group_reg = re.compile(r'^[a-z0-9][a-z0-9_]*$')
indexer_opts = [
    cfg.Opt('resource_group_name', default="searchlight",
            help="The default base name for accessing Elasticsearch",
            type=types.String(regex=resource_group_reg)),
    cfg.StrOpt('notifications_topic', default="notifications",
               help="The default messaging notifications topic"),
    cfg.BoolOpt('mapping_use_doc_values', default=True,
                help='Use doc_values for mapped fields where applicable.'
                     'Allows lower memory usage at the cost of some disk '
                     'space. Recommended, especially in large deployments.'),
    cfg.BoolOpt('include_region_name', default=False,
                help='Whether or not to include region_name as a mapping '
                     'field and in documents. The value will be determined '
                     'from service_credentials and override_region_name for '
                     'each plugin.'),
    cfg.ListOpt('publishers',
                help='The global publishers configuration, '
                     'plugin can override this by setting their own publishers'
                )
]

CONF = cfg.CONF
CONF.register_opts(indexer_opts, group='resource_plugin')


class IndexBase(plugin.Plugin, metaclass=abc.ABCMeta):
    NotificationHandlerCls = None

    def __init__(self):
        self.options = cfg.CONF[self.get_config_group_name()]

        self.engine = searchlight.elasticsearch.get_api()
        self.document_type = self.get_document_type()

        # This will be populated at load time.
        self.child_plugins = []
        self.parent_plugin = None

    @property
    def index_helper(self):
        if not getattr(self, '_index_helper', None):
            self._index_helper = helper.IndexingHelper(self)
        return self._index_helper

    @property
    def name(self):
        return "%s-%s" % (self.resource_group_name, self.document_type)

    @property
    def mapping_use_doc_values(self):
        """Set to true to disable doc_values for a plugin's entire mapping"""
        if self.options.mapping_use_doc_values is not None:
            return self.options.mapping_use_doc_values
        else:
            return cfg.CONF.resource_plugin.mapping_use_doc_values

    @property
    def resource_group_name(self):
        if not getattr(self, '_group_name', None):
            if self.parent_plugin:
                self._group_name = self.parent_plugin.resource_group_name
                if self.options.resource_group_name is not None and  \
                        self.options.resource_group_name != self._group_name:
                    LOG.warning(
                        "Overriding resource_group for %(plugin)s because it "
                        "differs from parent plugin %(parent)s resource_group "
                        "%(resource_group)s" %
                        {"plugin": self.document_type,
                         "parent": self.parent_plugin.document_type,
                         "resource_group": self._group_name}
                    )
            else:
                if self.options.resource_group_name is not None:
                    self._group_name = self.options.resource_group_name
                elif cfg.CONF.resource_plugin.resource_group_name is not None:
                    self._group_name = \
                        cfg.CONF.resource_plugin.resource_group_name
                else:
                    self._group_name = "searchlight"
        return self._group_name

    @property
    def alias_name_listener(self):
        return "%s-listener" % self.resource_group_name

    @property
    def alias_name_search(self):
        return "%s-search" % self.resource_group_name

    @abc.abstractproperty
    def resource_allowed_policy_target(self):
        """Should return the policy target that this plugin's related service
        uses to determine who has API access to list resources. Can return None
        if this service doesn't support policy.
        """
        return None

    @abc.abstractproperty
    def service_type(self):
        """Should match the keystone catalog service type for a resource"""
        return None

    def prepare_index(self, index_name):
        """Prepare a new index for usage with this listener. We need to be
           called immediately after a new index is created, but before it
           gets associated with an alias. Prepping means we will add
           the settings and mapping for this listener's document type.
        """
        if self.parent_plugin_type():
            LOG.debug(
                "Skipping index prep for %(doc_type)s; will be handled by "
                "parent (%(parent_type)s)" %
                {"doc_type": self.document_type,
                 "parent_type": self.parent_plugin_type()})
            return

        self.check_mapping_sort_fields()
        for child_plugin in self.child_plugins:
            child_plugin.check_mapping_sort_fields()

        # Prepare the new index for this document type.
        self.setup_index_mapping(index_name=index_name)

    def setup_index_settings(self, index_name):
        """Update index settings. """
        index_settings = self.get_settings()
        if index_settings:
            self.engine.indices.put_settings(body=index_settings,
                                             index=index_name)

    def setup_index_mapping(self, index_name):
        """Update index document mapping."""
        # Using 'reversed' because in e-s 2.x, child mappings must precede
        # their parents, and the parent will be the first element
        for doc_type, mapping in self.get_full_mapping():
            self.engine.indices.put_mapping(index=index_name,
                                            doc_type=doc_type,
                                            body=mapping)

    def index_initial_data(self, index_name=None):
        """Insert all objects from a plugin (generally by API requests to its
        service) into an index assumed to have been created with
        prepare_index. If index_name is not set, the searchlight-listener alias
        will be used instead.
        """
        object_list = self.get_objects()
        documents = []
        versions = []
        for obj in object_list:
            document = self.serialize(obj)
            documents.append(document)
            if self.NotificationHandlerCls:
                version = self.NotificationHandlerCls.get_version(document)
            else:
                version = NotificationBase.get_version(document)
            versions.append(version)
        self.index_helper.save_documents(documents, versions=versions,
                                         index=index_name)

    def get_facets(self, request_context, all_projects=False, limit_terms=0,
                   include_fields=True, exclude_options=False):
        """Get facets available for searching, in the form of a list of
        dicts with keys "name", "type" and optionally "options" if a field
        should have discreet allowed values. If include_fields is false,
        only the total doc count will be requested.
        """
        exclude_facets = self.facets_excluded
        is_admin = request_context.is_admin

        def include_facet(name):
            if name not in exclude_facets:
                return True

            if is_admin and exclude_facets[name]:
                return True

            return False

        def get_facets_for(property_mapping, meta_mapping, prefix='',
                           inside_nested=None):
            mapping_facets = []
            for name, properties in property_mapping.items():
                property_type = properties.get('type', 'object')
                if property_type in ('nested', 'object'):
                    if include_facet(prefix + name):
                        is_nested = property_type == 'nested'
                        mapping_facets.extend(
                            get_facets_for(properties['properties'],
                                           meta_mapping,
                                           "%s%s." % (prefix, name),
                                           inside_nested=is_nested))
                else:
                    indexed = properties.get('index', None) != 'no'
                    if indexed and include_facet(name):
                        facet_name = prefix + name
                        mapping_facet = {
                            'name': facet_name,
                            'type': property_type
                        }

                        # If we're inside either an object or nested object,
                        # add that to the mapping too
                        if inside_nested is not None:
                            mapping_facet['nested'] = inside_nested

                        # Add raw field if it's an analyzed field,
                        # aggregation on analyzed string field doesn't
                        # work well
                        if (properties['type'] == 'string' and
                                properties.get('index') != 'not_analyzed' and
                                'raw' in properties.get('fields', {})):
                            mapping_facet['facet_field'] = facet_name + '.raw'

                        # Plugin can specify _meta mapping to link an id with a
                        # resource type, which can be used by Client program/UI
                        # to GET more information from the resource type.
                        # See https://www.elastic.co/guide/en/elasticsearch/
                        # reference/2.1/mapping-meta-field.html
                        if facet_name in meta_mapping:
                            mapping_facet.update(meta_mapping[facet_name])

                        if (self.get_parent_id_field() and
                                name == self.get_parent_id_field()):
                            mapping_facet['parent'] = True
                            if 'resource_type' not in mapping_facet:
                                mapping_facet['resource_type'] = \
                                    self.parent_plugin_type()

                        mapping_facets.append(mapping_facet)

            return mapping_facets

        facets = []
        if include_fields:
            facets = get_facets_for(self.get_mapping()['properties'],
                                    self.get_mapping().get('_meta', {}))

        # Don't retrieve facet terms for any excluded fields
        included_fields = set(f['name'] for f in facets)
        options_fields = set(self.facets_with_options) & included_fields

        raw_fields = dict([(f['name'], f['facet_field'])
                           for f in facets
                           if f.get('facet_field')])
        # If field has a raw field, use a tuple of field name and
        # raw field name
        facet_terms_for = [(field, raw_fields[field])
                           if field in raw_fields
                           else field
                           for field in options_fields]

        facet_terms, doc_count = self._get_facet_terms(
            facet_terms_for, request_context, all_projects,
            limit_terms=limit_terms, exclude_options=exclude_options)

        if include_fields:
            for facet in facets:
                if facet['name'] in facet_terms:
                    facet['options'] = facet_terms[facet['name']]

        return facets, doc_count

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
                         all_projects, limit_terms,
                         exclude_options=False):
        # Fields can be empty if there are no facet terms desired,
        # but we will run a size=0 search to get the doc count. If the
        # user does not want the options associated with the facet fields,
        # do not aggregate. This is controlled with a parameter to the
        # API call.
        body = {}
        term_aggregations = {}

        if fields:
            mapping = self.get_mapping()['properties']
            # Nested fields will be all the mapped fields with type=='nested'
            # Not tremendously keen on the way this is structured but the
            # nested fields are a bit special case
            nested_fields = [name
                             for name, properties in mapping.items()
                             if properties['type'] == 'nested']
            if not exclude_options:
                term_aggregations = utils.get_facets_query(fields,
                                                           nested_fields,
                                                           limit_terms)
            if term_aggregations:
                body['aggs'] = term_aggregations

        role_filter = request_context.user_role_filter

        filter_query = {
            "bool": {
                "filter": {
                    "bool": {
                        "must": {
                            "term": {ROLE_USER_FIELD: role_filter}
                        }
                    }
                }
            }
        }

        # Add in the RBAC filters unless all_projects is requested
        if not (request_context.is_admin and all_projects):
            rbac_filters = self._get_rbac_field_filters(request_context)

            # minimum_should_match:1 is assumed in filter context,
            # but I'm including it explicitly so nobody spends an hour
            # scouring the documentation to check that is the case
            if rbac_filters:
                filter_query["bool"]["filter"]["bool"].update(
                    {"should": self._get_rbac_field_filters(request_context),
                     "minimum_should_match": 1})

        body['query'] = filter_query

        results = self.engine.search(
            index=self.alias_name_search,
            doc_type=self.get_document_type(),
            body=body,
            ignore_unavailable=True,
            size=0)

        agg_results = results.get('aggregations', {})
        doc_count = results['hits']['total']

        facet_terms = utils.transform_facets_results(
            agg_results,
            self.get_document_type())

        if term_aggregations and not agg_results:
            LOG.warning(
                "No aggregations found for %(resource_type)s. There may "
                "be a mapping problem." %
                {'resource_type': self.get_document_type()})
        return facet_terms, doc_count

    def check_mapping_sort_fields(self):
        """Check that fields that are expected to define a 'raw' field do so"""
        fields_needing_raw = searchlight.elasticsearch.RAW_SORT_FIELDS
        mapped_properties = self.get_mapping().get('properties', {})
        for field_name, field_mapping in mapped_properties.items():
            if field_name in fields_needing_raw:
                raw = field_mapping.get('fields', {}).get('raw', None)
                if not raw:
                    msg_vals = {"field_name": field_name,
                                "index_name": self.alias_name_listener,
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
        should also be mapped to _id in the elasticsearch mapping, though
        under role-based filtering, it will be modified to avoid clashes.
        """
        return "id"

    @classmethod
    def parent_plugin_type(cls):
        """If set, should be the resource type (canonical name) of
        the parent. Setting this for a plugin means that plugin cannot be
        initially indexed on its own, only as part of the parent indexing.
        """
        return None

    def get_parent_id_field(self):
        """Whatever field should be treated as the parent id. This is required
        for plugins with _parent definitions in their mappings. Documents to be
        indexed should contain this field.
        """
        return None

    @property
    def routing_field(self):
        """Whatever field should be treated as the routing value. Whatever is
        used must be available to all notifications on the child since
        index/update/delete operations will all require it. Additionally, if
        it is NOT the parent id, the parent plugin must be routed using the
        same field. This field is accessed AFTER serialization.
        """
        return None

    @property
    def include_region_name(self):
        return cfg.CONF.resource_plugin.include_region_name

    @property
    def region_name(self):
        """Returns a region name if enabled by config and configured in
        service_credentials. Adding it as per-plugin rather than global
        in case at some point per-plugin credentials are supported.
        """
        # Check the override in each plugin's options first, then use
        # whatever's in service_credentials
        region_name = self.options.override_region_name
        if region_name:
            return region_name
        region_name = getattr(CONF.service_credentials,
                              'os_region_name', None)
        if region_name:
            return [region_name]

    @property
    def enabled(self):
        return self.options.enabled

    @property
    def publishers(self):
        if self.options.publishers is not None:
            return self.options.publishers
        elif cfg.CONF.resource_plugin.publishers is not None:
            return cfg.CONF.resource_plugin.publishers

    @property
    def allow_admin_ignore_rbac(self):
        """If set for a plugin, an administrative query for all_projects will
        NOT skip RBAC filters.
        """
        return True

    @classmethod
    def get_document_type(cls):
        """Get name of the document type.

        This is in the format of OS::Service::Resource typically.
        """
        raise NotImplementedError()

    def register_parent(self, parent):
        if not self.parent_plugin:
            parent.child_plugins.append(self)
            self.parent_plugin = parent

    def get_query_filters(self, request_context, ignore_rbac=False):
        """Gets an index/type filter as es json filter dsl, and include
        plugin-specific RBAC filter terms unless `ignore_rbac` is True
        (for admin queries).
        """
        query_filter = {
            'indices': {
                'index': self.alias_name_search,
                'no_match_query': 'none',
                'query': {
                    'bool': {
                        'filter': {
                            'bool': {
                                'must': {
                                    'type': {
                                        'value': self.get_document_type()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        if not (ignore_rbac and self.allow_admin_ignore_rbac):
            rbac_filters = self._get_rbac_field_filters(request_context)
            if rbac_filters:
                bool_clause = query_filter['indices']['query']['bool']
                bool_clause['filter']['bool'].update({
                    'should': rbac_filters,
                    'minimum_should_match': 1})

        return query_filter

    @abc.abstractmethod
    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters in a list to be injected into an
        indices query. Document type will be added. The filters will be used
        in the 'should' filter clause (i.e. OR).
        """

    def get_notification_handler(self):
        """Get the notification handler which implements NotificationBase."""
        if self.NotificationHandlerCls:
            return self.NotificationHandlerCls(self.index_helper,
                                               self.options)
        return None

    def filter_result(self, hit, request_context):
        """Filter each outgoing search result; document in hit['_source'].
        """
        if 'highlight' in hit:
            # We need to clean up any fields 'leaked' by highlighting.
            # As a reminder since this is a rare case, the 'highlight'
            # dict is a peer of '_source' in the overall hit structure.
            hit['highlight'].pop(ROLE_USER_FIELD, None)

    @abc.abstractmethod
    def get_mapping(self):
        """Get an index mapping."""

    def get_full_mapping(self):
        """Gets the full mapping doc for this type, including children. This
        returns a child-first (depth-first) generator.
        """
        # Assemble the children!
        for child_plugin in self.child_plugins:
            for plugin_type, mapping in child_plugin.get_full_mapping():
                yield plugin_type, mapping

        type_mapping = self.get_mapping()

        # Add common mapping fields
        # ROLE_USER_FIELD is required for RBAC by all plugins
        type_mapping['properties'][ROLE_USER_FIELD] = {
            'type': 'string',
            'index': 'not_analyzed',
            'include_in_all': False
        }

        # Add region name
        if self.include_region_name:
            type_mapping['properties']['region_name'] = {
                'type': 'string',
                'index': 'not_analyzed',
            }

        if 'updated_at' not in type_mapping['properties'].keys():
            type_mapping['properties']['updated_at'] = {'type': 'date'}

        if self.mapping_use_doc_values:
            helper.IndexingHelper.apply_doc_values(type_mapping)

        expected_parent_type = self.parent_plugin_type()
        mapping_parent = type_mapping.get('_parent', None)
        if mapping_parent:
            if mapping_parent['type'] != expected_parent_type:
                raise exception.IndexingException(
                    _("Mapping for '%(doc_type)s' contains a _parent "
                      "'%(actual)s' that doesn't match '%(expected)s'") %
                    {"doc_type": self.document_type,
                     "actual": mapping_parent['type'],
                     "expected": expected_parent_type})
        elif expected_parent_type:
            type_mapping['_parent'] = {'type': expected_parent_type}

        yield self.document_type, type_mapping

    @classmethod
    def get_plugin_type(cls):
        return "resource_plugin"

    @classmethod
    def get_plugin_name(cls):
        return cls.get_document_type().replace("::", "_").lower()

    @property
    def admin_only_fields(self):
        admin_only = self.options.admin_only_fields
        if not admin_only:
            return []
        return self.options.admin_only_fields.split(',')

    @property
    def requires_role_separation(self):
        return len(self.admin_only_fields) > 0

    @classmethod
    def is_plugin_enabled_by_default(cls):
        '''
        Each plugin can overwrite the default value of whether a
        plugin should be enabled if the value is not explicitly
        set in the configuration

        '''
        return True

    @classmethod
    def get_plugin_opts(cls):
        """Options that can be overridden per plugin.
        """
        opts = [
            cfg.StrOpt("resource_group_name"),
            cfg.BoolOpt("enabled", default=cls.is_plugin_enabled_by_default()),
            cfg.StrOpt("admin_only_fields"),
            cfg.BoolOpt('mapping_use_doc_values'),
            cfg.ListOpt('override_region_name',
                        help="Override the region name configured in "
                             "'service_credentials'. This is useful when a "
                             "service is deployed as a cloud-wide service "
                             "rather than per region (e.g. Region1,Region2)."),
            cfg.ListOpt('publishers',
                        help='Used to configure publishers for the plugin, '
                             'value could be publisher names configured in '
                             'setup.cfg file.'
                        )
        ]
        if cls.NotificationHandlerCls:
            opts.extend(cls.NotificationHandlerCls.get_plugin_opts())
        return opts

    @classmethod
    def get_config_group_name(cls):
        """Override the get_plugin_name in order to use the document type as
        plugin name. This turns OS::Service::Resource to os_service_resource
        """
        config_name = cls.get_document_type().replace("::", "_").lower()
        return "resource_plugin:%s" % config_name


class NotificationBase(object, metaclass=abc.ABCMeta):

    def __init__(self, index_helper, options):
        self.index_helper = index_helper
        self.plugin_options = options

    def get_notification_supported_events(self):
        """Get the list of event types this plugin responds to."""
        return list(self.get_event_handlers().keys())

    def get_log_fields(self, event_type, payload):
        """Return an iterable of key value pairs in payload that will be
        present in notification log messages. Document type, event type, timing
        and tenant information will be prepended.
        """
        if 'id' in payload:
            return ('id', payload['id']),
        return ()

    @abc.abstractmethod
    def get_event_handlers(self):
        """Returns a mapping of event name to function"""

    @classmethod
    def _get_notification_exchanges(cls):
        """Return a list of oslo exchanges this plugin cares about"""

    @classmethod
    def get_plugin_opts(cls):
        opts = []
        exchanges = cls._get_notification_exchanges()
        if exchanges:
            defaults = " ".join("<notifications_topic>,%s" % i
                                for i in exchanges)
            opts.append(cfg.MultiOpt(
                'notifications_topics_exchanges',
                item_type=types.MultiString(),
                help='Override default topic,exchange pairs. '
                     'Defaults to %s' % defaults,
                default=[]))
        return opts

    def process(self, ctxt, publisher_id, event_type, payload, metadata):
        """Process the incoming notification message."""
        try:
            docs = self.get_event_handlers()[event_type](
                event_type,
                payload,
                metadata['timestamp'])
            if docs:
                if not hasattr(docs, '__iter__'):
                    docs = [docs]
            return docs
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))

    def get_notification_topics_exchanges(self):
        """"Returns a list of (topic,exchange), (topic,exchange)..)
        This will either be (CONF.notifications_topic,<exchange>) for
        each exchange in _get_notification_exchanges OR the list of
        values for CONF.plugin.notifications_topics_exchanges.
        """
        configured = self.plugin_options.notifications_topics_exchanges
        if configured:
            return [tuple(i.split(',')) for i in configured]
        else:
            return [(CONF.resource_plugin.notifications_topic, exchange)
                    for exchange in self._get_notification_exchanges()]

    @classmethod
    def get_version(cls, payload, timestamp=None, preferred_date_field=None):
        """Combine <preferred_date_field>|updated_at|created_at epoch with
        notification timestamp as a version number, format is
        <right 9 digits update epoch(create epoch)><right 9 digits timestamp
        in milliseconds>, if timestamp is not present(sync indexing), fill in
        9 digits of zero instead.

        The reason we combine update time and timestamp together is the
        precision of update time is limit to seconds. It's not accurate enough
        to use as a version.

        The max version in Elasticsearch is 9.2e+18, allowing 19 digits at
        most. Our version is 18 digits long, leaves 1 digit for conservation.

        The updated epoch is 10 digits long, we strip off its leading digit,
        concatenate it with the right 9 digits of timestamp in milliseconds,
        and we get a 18 digits long version.

        The truncating has some potential things to be noted, similar to Y2K
        problem.

        Let's say we have an updated epoch 1450161655. Stripping off the
        leading '1' from the current epoch seconds 'rebases' our epoch around
        1984(450161655). By the time we get to an updated epoch beginning '199'
        we're somewhere around 2033, and truncating epoch to 2001. Once the
        clock flips round to begin '200'(year 2033) things will stop working
        because we'll suddenly be using epoch that look like they're from 1969.
        We can address this before that happens; worst case is that you'd have
        to reindex everything, or reset the version.

        The "timestamp" has similar issues. When the "timestamp" overflowed
        the 9-digit field, time becomes indistinguishable. The 9 digits
        millisecond precision gives us around 27 hours. It should be enough to
        distinguish notifications with different timestamps.
        """
        updated = None

        # Pick the best/preferred date field to calculate version from
        date_fields = ('updated_at', 'created_at', 'deleted_at')
        if preferred_date_field:
            date_fields = (preferred_date_field,) + date_fields

        for date_field in date_fields:
            if date_field and payload.get(date_field):
                updated = payload.get(date_field)
                break
        else:
            date_fields_str = ', '.join(date_fields)
            msg = ('Failed to build elasticsearch version; none of %(dfs)s '
                   'found in payload: %(payload)s' %
                   {'dfs': date_fields_str, 'payload': payload})
            raise exception.SearchlightException(message=msg)

        updated_obj = timeutils.parse_isotime(updated)
        updated_epoch = int(calendar.timegm(updated_obj.utctimetuple()))
        if timestamp:
            timestamp_obj = timeutils.parse_isotime(timestamp)
            timestamp_epoch = int(calendar.timegm(
                timestamp_obj.utctimetuple()))
            timestamp_milli = (timestamp_epoch * 1000 +
                               timestamp_obj.microsecond // 1000)
            truncate_timestamp = str(timestamp_milli)[-9:].zfill(9)
            # truncate updated epoch because we are run out of numbers.
            final_stamp = int(str(updated_epoch)[-9:] +
                              str(truncate_timestamp))
        else:
            final_stamp = int(str(updated_epoch)[-9:] + '0' * 9)
        return final_stamp
