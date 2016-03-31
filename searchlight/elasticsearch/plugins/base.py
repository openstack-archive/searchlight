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
import oslo_messaging
from oslo_utils import encodeutils
from oslo_utils import timeutils
import six

from searchlight.common import exception
import searchlight.elasticsearch
from searchlight.elasticsearch.plugins import utils
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight import i18n
from searchlight import plugin

LOG = logging.getLogger(__name__)
_LW = i18n._LW
_LI = i18n._LI
_ = i18n._

indexer_opts = [
    cfg.StrOpt('resource_group_name', default="searchlight",
               help="The default base name for accessing Elasticsearch"),
    cfg.StrOpt('notifications_topic', default="searchlight_indexer",
               help="The default messaging notifications topic"),
    cfg.BoolOpt('mapping_use_doc_values', default=True,
                help='Use doc_values for mapped fields where applicable.'
                     'Allows lower memory usage at the cost of some disk '
                     'space. Recommended, especially in large deployments.')
]

CONF = cfg.CONF
CONF.register_opts(indexer_opts, group='resource_plugin')


@six.add_metaclass(abc.ABCMeta)
class IndexBase(plugin.Plugin):
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
            self._index_helper = utils.IndexingHelper(self)
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
            # We no longer allow this to be set per-plugin. See note in
            # get_plugin_opts()
            if cfg.CONF.resource_plugin.resource_group_name is not None:
                self._group_name = cfg.CONF.resource_plugin.resource_group_name
            else:
                self._group_name = "searchlight"
        return self._group_name

    @property
    def alias_name_listener(self):
        return "%s-listener" % self.resource_group_name

    @property
    def alias_name_search(self):
        return "%s-search" % self.resource_group_name

    def prepare_index(self, index_name):
        """Prepare a new index for usage with this listener. We need to be
           caled immediately after a new index is created, but before it
           gets associated with an alias. Prepping means we will add
           the settings and mapping for this listener's document type.
        """
        if self.parent_plugin_type():
            LOG.debug(_LI(
                "Skipping index prep for %(doc_type)s; will be handled by"
                "parent (%(parent_type)s)") %
                {"doc_type": self.document_type,
                 "parent_type": self.parent_plugin_type()})
            return

        self.check_mapping_sort_fields()
        for child_plugin in self.child_plugins:
            child_plugin.check_mapping_sort_fields()

        # Prepare the new index for this document type.
        self.setup_index_settings(index_name=index_name)
        self.setup_index_mapping(index_name=index_name)

    def initial_indexing(self, index_name=None, setup_data=True):
        """Add data for this resource type. This method is called per plugin.
           The assumption is that the aliases/indexes have already been setup
           correctly before calling us. See the comments in the method
           cmd/manage.py::sync() for more details.
        """
        if self.parent_plugin_type():
            LOG.debug(_LI(
                "Skipping initialization for %(doc_type)s; will be handled by"
                "parent (%(parent_type)s)") %
                {"doc_type": self.document_type,
                 "parent_type": self.parent_plugin_type()})
            return

        if setup_data:
            self.setup_data(index_name)

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

    def setup_data(self, index=None):
        """Insert all objects from database into search engine.
           We are assuming this helper method is called by initial_indexing().
           If you wish to call this method from somewhere else, please make
           sure you understand the usage of the "index" parameter. See the
           comment in plugins/utils.py::save_documents() for more details.
        """
        object_list = self.get_objects()
        documents = []
        versions = []
        for obj in object_list:
            document = self.serialize(obj)
            documents.append(document)
            version = self.NotificationHandlerCls.get_version(document)
            versions.append(version)
        self.index_helper.save_documents(documents, versions=versions,
                                         index=index)

        for child_plugin in self.child_plugins:
            child_plugin.setup_data(index)

    def get_facets(self, request_context, all_projects=False, limit_terms=0):
        """Get facets available for searching, in the form of a list of
        dicts with keys "name", "type" and optionally "options" if a field
        should have discreet allowed values
        """
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
                    indexed = properties.get('index', None) != 'no'
                    if indexed and include_facet(name):
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
        term_aggregations = utils.get_facets_query(fields, limit_terms)

        if term_aggregations:
            body = {
                'aggs': term_aggregations,
            }

            role_filter = request_context.user_role_filter
            plugin_filters = [{
                "term": {ROLE_USER_FIELD: role_filter}
            }]
            if not (request_context.is_admin and all_projects):
                plugin_filters.extend(
                    self._get_rbac_field_filters(request_context))

            body['query'] = {
                "filtered": {
                    "filter": {
                        "and": plugin_filters
                    }}}

            results = self.engine.search(
                index=self.alias_name_search,
                doc_type=self.get_document_type(),
                body=body,
                ignore_unavailable=True,
                search_type='count')

            agg_results = results.get('aggregations', {})
            facet_terms = utils.transform_facets_results(
                agg_results,
                self.get_document_type())

            if not agg_results:
                LOG.warning(_LW(
                    "No aggregations found for %(resource_type)s. There may "
                    "be a mapping problem.") %
                    {'resource_type': self.get_document_type()})
            return facet_terms
        return {}

    def check_mapping_sort_fields(self):
        """Check that fields that are expected to define a 'raw' field do so"""
        fields_needing_raw = searchlight.elasticsearch.RAW_SORT_FIELDS
        mapped_properties = self.get_mapping().get('properties', {})
        for field_name, field_mapping in six.iteritems(mapped_properties):
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
        """Whatever field should be treated as the routing value.
        This is required for plugins which want to base all the CRUD
        operations based on the _routing definition.
        """
        return None

    @property
    def enabled(self):
        return self.options.enabled

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
        raise NotImplemented()

    def register_parent(self, parent):
        if not self.parent_plugin:
            parent.child_plugins.append(self)
            self.parent_plugin = parent

    def get_index_display_name(self, indent_level=0):
        """The string used to list this plugin when indexing"""
        display = '\n' + '    ' * indent_level + '--> ' if indent_level else ''

        display += '%s' % (self.document_type)
        display += ''.join(c.get_index_display_name(indent_level + 1)
                           for c in self.child_plugins)
        return display

    def get_query_filters(self, request_context, ignore_rbac=False):
        """Gets an index/type filter as es json filter dsl, and include
        plugin-specific RBAC filter terms unless `ignore_rbac` is True
        (for admin queries).
        """
        query_filter = {
            'indices': {
                'index': self.alias_name_search,
                'no_match_filter': 'none',
                'filter': {
                    'and': [
                        {'type': {'value': self.get_document_type()}}
                    ]
                }
            }
        }

        if not (ignore_rbac and self.allow_admin_ignore_rbac):
            rbac_filters = self._get_rbac_field_filters(request_context)
            query_filter['indices']['filter']['and'].extend(rbac_filters)

        return query_filter

    @abc.abstractmethod
    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return []

    def get_notification_handler(self):
        """Get the notification handler which implements NotificationBase."""
        if self.NotificationHandlerCls:
            return self.NotificationHandlerCls(self.index_helper,
                                               self.options)
        return None

    def filter_result(self, hit, request_context):
        """Filter each outgoing search result; document in hit['_source']. By
        default, this does nothing since information shouldn't be indexed.
        """
        pass

    def get_settings(self):
        """Get an index settings."""
        return {
            "index": {
                "gc_deletes": CONF.elasticsearch.index_gc_deletes
            }
        }

    def get_mapping(self):
        """Get an index mapping."""
        return {}

    def get_full_mapping(self):
        """Gets the full mapping doc for this type, including children. This
        returns a child-first (depth-first) generator.
        """
        # Assemble the children!
        for child_plugin in self.child_plugins:
            for plugin_type, mapping in child_plugin.get_full_mapping():
                yield plugin_type, mapping

        type_mapping = self.get_mapping()

        def apply_rbac_field(mapping):
            mapping['properties'][ROLE_USER_FIELD] = {
                'type': 'string',
                'index': 'not_analyzed',
                'include_in_all': False
            }

        apply_rbac_field(type_mapping)

        if self.mapping_use_doc_values:
            utils.IndexingHelper.apply_doc_values(type_mapping)

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
        """Options that can be overridden per plugin. Note that
        resource_group_name is not present while we determine a fix for
        running has_parent/has_child queries across indices with different
        sets of types (https://bugs.launchpad.net/searchlight/+bug/1558240)
        """
        opts = [
            cfg.BoolOpt("enabled", default=cls.is_plugin_enabled_by_default()),
            cfg.StrOpt("admin_only_fields"),
            cfg.BoolOpt('mapping_use_doc_values')
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


@six.add_metaclass(abc.ABCMeta)
class NotificationBase(object):

    def __init__(self, index_helper, options):
        self.index_helper = index_helper
        self.plugin_options = options

    def get_notification_supported_events(self):
        """Get the list of event types this plugin responds to."""
        return list(six.iterkeys(self.get_event_handlers()))

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
        LOG.debug("Received %s event for %s",
                  event_type,
                  self.index_helper.document_type)
        try:
            self.get_event_handlers()[event_type](payload,
                                                  metadata['timestamp'])
            return oslo_messaging.NotificationResult.HANDLED
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

        The "timestamp" has similiar issues. When the "timestamp" overflowed
        the 9-digit field, time becomes indistinguishable. The 9 digits
        millisecond precision gives us around 27 hours. It should be enough to
        distinguish notifications with different timestamps.
        """
        updated = None

        # Pick the best/preferred date field to calculate version from
        date_fields = ('updated_at', 'created_at')
        if preferred_date_field:
            date_fields = (preferred_date_field,) + date_fields

        for date_field in date_fields:
            if date_field and payload.get(date_field):
                updated = payload.get(date_field)
                break
        else:
            date_fields_str = ', '.join(date_fields)
            msg = ('Failed to build elasticsearch version; none of %s'
                   'found in payload: %s' % (date_fields_str, payload))
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
            return '%s%s' % (str(updated_epoch)[-9:], truncate_timestamp)
        else:
            return '%s%s' % (str(updated_epoch)[-9:], '0' * 9)
