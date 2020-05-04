# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from elasticsearch import exceptions as es_exc
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
import webob.exc

from searchlight.api import policy
from searchlight.common import exception
from searchlight.common import utils
from searchlight.common import wsgi
import searchlight.elasticsearch
import searchlight.gateway
from searchlight.i18n import _


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class SearchController(object):
    def __init__(self, plugins=None, es_api=None, policy_enforcer=None):
        self.es_api = es_api or searchlight.elasticsearch.get_api()
        self.policy = policy_enforcer or policy.Enforcer()
        self.gateway = searchlight.gateway.Gateway(
            es_api=self.es_api,
            policy_enforcer=self.policy)
        self.plugins = plugins or {}

    def search(self, req, query, index=None, doc_type=None,
               from_=0, size=None, **kwargs):
        """Supported kwargs:
        :param _source:
        :param _source_include:
        :param _source_exclude:
        :return:
        """
        if size is None:
            size = CONF.limit_param_default

        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            result = search_repo.search(index,
                                        doc_type,
                                        query,
                                        from_,
                                        size,
                                        ignore_unavailable=True,
                                        **kwargs)

            hits = result.get('hits', {}).get('hits', [])
            try:
                # Note that there's an assumption that the plugin resource
                # type is always the same as the document type. If this is not
                # the case in future, a reverse lookup's needed
                for hit in hits:
                    plugin = self.plugins[hit['_type']].obj
                    plugin.filter_result(hit, req.context)
            except KeyError as e:
                raise Exception("No registered plugin for type %s" % e.message)
            return result
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except exception.Duplicate as e:
            raise webob.exc.HTTPConflict(explanation=e.msg)
        except es_exc.RequestError:
            msg = _("Query malformed or search parse failure, please check "
                    "the syntax")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def plugins_info(self, req, doc_type):
        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            return search_repo.plugins_info(doc_type)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def facets(self, req, index_name=None, doc_type=None,
               all_projects=False, limit_terms=0, include_fields=True,
               exclude_options=False):
        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            return search_repo.facets(index_name, doc_type,
                                      all_projects, limit_terms,
                                      include_fields=include_fields,
                                      exclude_options=exclude_options)
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    _disallowed_properties = ['self', 'schema']

    def __init__(self, plugins, schema=None, policy_enforcer=None):
        super(RequestDeserializer, self).__init__()
        self.plugins = plugins
        self.policy_enforcer = policy_enforcer or policy.Enforcer()

    def _get_request_body(self, request):
        output = super(RequestDeserializer, self).default(request)
        if 'body' not in output:
            msg = _('Body expected in request.')
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return output['body']

    @classmethod
    def _check_allowed(cls, query):
        for key in cls._disallowed_properties:
            if key in query:
                msg = _("Attribute '%s' is read-only.") % key
                raise webob.exc.HTTPForbidden(explanation=msg)

    def _get_available_resource_types(self):
        return self.plugins.keys()

    def _validate_resource_type(self, resource_type):
        if resource_type not in self._get_available_resource_types():
            msg = _("Resource type '%s' is not supported.") % resource_type
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return resource_type

    def _get_index_doc_types(self, resource_types):
        indices, doc_types = set(), set()
        for resource_type in resource_types:
            plugin = self.plugins[resource_type].obj
            indices.add(plugin.alias_name_search)
            doc_types.add(plugin.get_document_type())
        return list(indices), list(doc_types)

    def _get_available_indices(self, types=[]):
        return list(set(p.obj.alias_name_search
                        for p in self.plugins.values()
                        if p.obj.get_document_type() in types or not types))

    def _get_available_types(self):
        return list(set(p.obj.get_document_type()
                        for p in self.plugins.values()))

    def _filter_types_by_policy(self, context, types):
        def _allowed(_type):
            return policy.plugin_allowed(
                self.policy_enforcer, context, self.plugins[_type].obj)

        allowed_types = list(filter(_allowed, types))
        if not allowed_types:
            disallowed_str = ", ".join(sorted(types))
            msg = _("There are no resource types accessible to you to serve "
                    "your request. You do not have access to the "
                    "following resource types: %s") % disallowed_str
            raise webob.exc.HTTPForbidden(explanation=msg)
        return allowed_types

    def _validate_index(self, index):
        available_indices = self._get_available_indices()

        if index not in available_indices:
            msg = _("Index '%s' is not supported.") % index
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return index

    def _validate_doc_type(self, doc_type):
        available_types = self._get_available_types()

        if doc_type not in available_types:
            msg = _("Document type '%s' is not supported.") % doc_type
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return doc_type

    def _validate_integer_param(self, value, gte, param_name):
        try:
            value = int(value)
        except ValueError:
            msg = _("%s param must be an integer") % param_name
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if value < gte:
            msg = _("%(param_name)s param must be greater than or equal "
                    "to %(gte)s") % {'param_name': param_name, 'gte': gte}
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return value

    def _validate_offset(self, offset, from_):
        if offset is not None and from_ is not None:
            msg = "Provide 'offset' or 'from', but not both"
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if offset is not None:
            return self._validate_integer_param(offset, 0, 'offset')
        elif from_ is not None:
            return self._validate_integer_param(from_, 0, 'from')

        return None

    def _validate_limit(self, limit, size):
        if limit is not None and size is not None:
            msg = "Provide 'limit' or 'size', but not both"
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit is not None:
            return self._validate_integer_param(limit, 0, 'limit')
        elif size is not None:
            return self._validate_integer_param(size, 0, 'size')

        return None

    def _validate_actions(self, actions):
        if not actions:
            msg = _("actions param cannot be empty")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        output = []
        allowed_action_types = ['create', 'update', 'delete', 'index']
        for action in actions:
            action_type = action.get('action', 'index')
            document_id = action.get('id')
            document_type = action.get('type')
            index_name = action.get('index')
            data = action.get('data', {})
            script = action.get('script')

            if index_name is not None:
                index_name = self._validate_index(index_name)

            if document_type is not None:
                document_type = self._validate_doc_type(document_type)

            if action_type not in allowed_action_types:
                msg = _("Invalid action type: '%s'") % action_type
                raise webob.exc.HTTPBadRequest(explanation=msg)
            elif (action_type in ['create', 'update', 'index'] and
                    not any([data, script])):
                msg = (_("Action type '%s' requires data or script param.") %
                       action_type)
                raise webob.exc.HTTPBadRequest(explanation=msg)
            elif action_type in ['update', 'delete'] and not document_id:
                msg = (_("Action type '%s' requires ID of the document.") %
                       action_type)
                raise webob.exc.HTTPBadRequest(explanation=msg)

            bulk_action = {
                '_op_type': action_type,
                '_id': document_id,
                '_index': index_name,
                '_type': document_type,
            }

            if script:
                data_field = 'params'
                bulk_action['script'] = script
            elif action_type == 'update':
                data_field = 'doc'
            else:
                data_field = '_source'

            bulk_action[data_field] = data

            output.append(bulk_action)
        return output

    def _validate_aggregations(self, context, aggregations):
        if aggregations:
            # Check aggregations against policy
            try:
                self.policy_enforcer.enforce(context,
                                             'search:query:aggregations',
                                             context.policy_target)
            except exception.Forbidden as e:
                raise webob.exc.HTTPForbidden(explanation=e.msg)

            # Reject any requests including the 'global' aggregation type
            # because it bypasses RBAC. 'global' aggregations can only occur
            # at the top level, so we only need to check that level
            for agg_name, agg_definition in aggregations.items():
                if 'global' in agg_definition:
                    msg = _(
                        "Aggregation '%s' contains the 'global' aggregation "
                        "which is not allowed") % agg_name
                    LOG.error(msg)
                    raise webob.exc.HTTPForbidden(explanation=msg)
        return aggregations

    def _get_es_query(self, context, query, resource_types,
                      all_projects=False):
        is_admin = context.is_admin
        ignore_rbac = is_admin and all_projects

        type_and_rbac_filters = []
        for resource_type in resource_types:
            plugin = self.plugins[resource_type].obj

            try:
                plugin_filter = plugin.get_query_filters(
                    context, ignore_rbac=ignore_rbac)

                type_and_rbac_filters.append(plugin_filter)
            except Exception as e:
                msg = _("Error processing %s RBAC filter") % resource_type
                LOG.error("Failed to retrieve RBAC filters "
                          "from search plugin "
                          "%(ext)s: %(e)s" %
                          {'ext': plugin.name, 'e': e})
                raise webob.exc.HTTPInternalServerError(explanation=msg)

        role_filter = {'term': {searchlight.elasticsearch.ROLE_USER_FIELD:
                                context.user_role_filter}}

        # Create a filter query for the role filter; RBAC filters are added
        # in the next step
        es_query = {
            'bool': {
                'filter': {
                    'bool': {
                        'must': role_filter
                    }
                },
                'must': query
            }
        }

        if type_and_rbac_filters:
            # minimum_should_match: 1 is assumed in filter context,
            # but I'm including it explicitly so nobody spends an
            # hour scouring the documentation to check
            es_query['bool']['filter']['bool'].update(
                {'should': type_and_rbac_filters,
                 'minimum_should_match': 1})
        return {'query': es_query}

    def _get_sort_order(self, sort_order):
        if isinstance(sort_order, (str, dict)):
            # Elasticsearch expects a list
            sort_order = [sort_order]
        elif not isinstance(sort_order, list):
            msg = _("'sort' must be a string, dict or list")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        def replace_sort_field(sort_field):
            # Make some alterations for fields that have a 'raw' field so
            # that documents aren't sorted by tokenized values
            if isinstance(sort_field, str):
                # Raw field name
                if sort_field in searchlight.elasticsearch.RAW_SORT_FIELDS:
                    return sort_field + ".raw"
            elif isinstance(sort_field, dict):
                for field_name, sort_params in sort_field.items():
                    if field_name in searchlight.elasticsearch.RAW_SORT_FIELDS:
                        # There should only be one object
                        return {field_name + ".raw": sort_params}
            else:
                msg = "Unhandled sort type replacing '%s'" % sort_field
                raise webob.exc.HTTPInternalServerError(explanation=msg)
            return sort_field

        return [replace_sort_field(f) for f in sort_order]

    def _set_highlight_queries(self, highlight, query):
        """If no 'highlight_query' is given, use the input query to avoid
        highlighting all the filter terms we add for RBAC.
        """
        highlight_fields = highlight.get('fields', {})
        for field_name, highlight_params in highlight_fields.items():
            if 'highlight_query' not in highlight_params:
                highlight_params['highlight_query'] = query

            # require_field_match defaults to True in es-2, and prevents
            # highlighting for a field-less query_string ("query": "web")
            # because the _all field doesn't count as matching any given field
            if 'require_field_match' not in highlight_params:
                highlight_params['require_field_match'] = False

    def search(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        query = body.pop('query', {"match_all": {}})
        indices = body.pop('index', None)
        types = body.pop('type', None)
        _source = body.pop('_source', None)
        offset = body.pop('offset', None)
        from_ = body.pop('from', None)
        limit = body.pop('limit', None)
        size = body.pop('size', None)
        highlight = body.pop('highlight', None)
        aggregations = body.pop('aggregations', None)
        if not aggregations:
            aggregations = body.pop('aggs', None)
        elif 'aggs' in body:
            raise webob.exc.HTTPBadRequest("A request cannot include both "
                                           "'aggs' and 'aggregations'")
        sort_order = body.pop('sort', None)
        # all_projects will determine whether an admin sees
        # filtered results or not
        all_projects = body.pop('all_projects', False)
        # Return _version with results?
        version = body.pop('version', None)

        aggregations = self._validate_aggregations(request.context,
                                                   aggregations)

        available_types = self._get_available_types()
        if not types:
            types = available_types
        else:
            if not isinstance(types, (list, tuple)):
                types = [types]

            for requested_type in types:
                if requested_type not in available_types:
                    msg = _("Resource type '%s' is not in the list of enabled "
                            "plugins") % requested_type
                    raise webob.exc.HTTPBadRequest(explanation=msg)

        # Filter the list by policy before determining which indices to use
        types = self._filter_types_by_policy(request.context, types)

        available_indices = self._get_available_indices(types)
        if not indices:
            indices = available_indices
        else:
            if not isinstance(indices, (list, tuple)):
                indices = [indices]

            for requested_index in indices:
                if requested_index not in available_indices:
                    msg = _("Index '%s' is not in the list of enabled "
                            "plugins") % requested_index
                    raise webob.exc.HTTPBadRequest(explanation=msg)

        if not isinstance(indices, (list, tuple)):
            indices = [indices]

        query_params = {
            'query': self._get_es_query(request.context, query, types,
                                        all_projects=all_projects)
        }

        # Apply an additional restriction to elasticsearch to speed things up
        # in addition to the RBAC filters
        query_params['index'] = indices
        query_params['doc_type'] = types

        # Don't set query_params['_source'] any more; we ALWAYS want to
        # exclude the role user field, so if the query specifies just
        # _source=<string>, put that in _source_include
        source_exclude = [searchlight.elasticsearch.ROLE_USER_FIELD]

        if _source is not None:
            if isinstance(_source, dict):
                if 'include' in _source:
                    query_params['_source_include'] = _source['include']
                if 'exclude' in _source:
                    if isinstance(_source['exclude'], str):
                        source_exclude.append(_source['exclude'])
                    else:
                        source_exclude.extend(_source['exclude'])
            elif isinstance(_source, (list, str)):
                query_params['_source_include'] = _source
            else:
                msg = _("'_source' must be a string, dict or list")
                raise webob.exc.HTTPBadRequest(explanation=msg)

        query_params['_source_exclude'] = source_exclude

        from_ = self._validate_offset(offset, from_)
        if from_ is not None:
            query_params['from_'] = from_

        size = self._validate_limit(limit, size)
        if size is not None:
            query_params['size'] = size

        if highlight is not None:
            self._set_highlight_queries(highlight, query)
            query_params['query']['highlight'] = highlight

        if aggregations is not None:
            query_params['query']['aggregations'] = aggregations

        if sort_order is not None:
            query_params['query']['sort'] = self._get_sort_order(sort_order)

        if version is not None:
            query_params['version'] = version

        return query_params

    def facets(self, request):
        all_projects = request.params.get('all_projects', 'false')
        include_fields = request.params.get('include_fields', 'true')
        exclude_options = request.params.get('exclude_options', 'false')

        available_types = request.params.get('type',
                                             self._get_available_types())
        if not isinstance(available_types, (list, tuple)):
            available_types = [available_types]

        doc_types = self._filter_types_by_policy(request.context,
                                                 available_types)
        return {
            'index_name': request.params.get('index', None),
            'doc_type': doc_types,
            'all_projects': all_projects.lower() == 'true',
            'include_fields': include_fields.lower() == 'true',
            'exclude_options': exclude_options.lower() == 'true',
            'limit_terms': int(request.params.get('limit_terms', 0))
        }

    def plugins_info(self, request):
        doc_types = self._filter_types_by_policy(request.context,
                                                 self._get_available_types())
        return {
            'doc_type': doc_types
        }


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema

    def search(self, response, query_result):
        body = jsonutils.dumps(query_result, ensure_ascii=False)
        response.unicode_body = str(body)
        response.content_type = 'application/json'

    def plugins_info(self, response, query_result):
        body = jsonutils.dumps(query_result, ensure_ascii=False)
        response.unicode_body = str(body)
        response.content_type = 'application/json'

    def facets(self, response, query_result):
        body = jsonutils.dumps(query_result, ensure_ascii=False)
        response.unicode_body = str(body)
        response.content_type = 'application/json'


def create_resource():
    """Search resource factory method"""
    plugins = utils.get_search_plugins()
    policy_enforcer = policy.Enforcer()
    deserializer = RequestDeserializer(plugins,
                                       policy_enforcer=policy_enforcer)
    serializer = ResponseSerializer()
    controller = SearchController(plugins, policy_enforcer=policy_enforcer)
    return wsgi.Resource(controller, deserializer, serializer)
