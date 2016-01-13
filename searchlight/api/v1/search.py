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

import json

from elasticsearch import exceptions as es_exc
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils
import six
import webob.exc

from searchlight.api import policy
from searchlight.common import exception
from searchlight.common import utils
from searchlight.common import wsgi
import searchlight.elasticsearch
import searchlight.gateway
from searchlight import i18n

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE

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
               offset=0, limit=10, **kwargs):
        """Supported kwargs:
        :param _source:
        :param _source_include:
        :param _source_exclude:
        :return:
        """
        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            result = search_repo.search(index,
                                        doc_type,
                                        query,
                                        offset,
                                        limit,
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

    def plugins_info(self, req):
        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            return search_repo.plugins_info()
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()

    def facets(self, req, index_name=None, doc_type=None,
               all_projects=False, limit_terms=0):
        try:
            search_repo = self.gateway.get_catalog_search_repo(req.context)
            result = search_repo.facets(index_name, doc_type,
                                        all_projects, limit_terms)
            return result
        except exception.Forbidden as e:
            raise webob.exc.HTTPForbidden(explanation=e.msg)
        except exception.NotFound as e:
            raise webob.exc.HTTPNotFound(explanation=e.msg)
        except Exception as e:
            LOG.error(encodeutils.exception_to_unicode(e))
            raise webob.exc.HTTPInternalServerError()


class RequestDeserializer(wsgi.JSONRequestDeserializer):
    _disallowed_properties = ['self', 'schema']

    def __init__(self, plugins, schema=None):
        super(RequestDeserializer, self).__init__()
        self.plugins = plugins

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
            indices.add(plugin.get_index_name())
            doc_types.add(plugin.get_document_type())
        return list(indices), list(doc_types)

    def _get_available_indices(self, types=[]):
        return list(set(p.obj.get_index_name()
                        for p in self.plugins.values()
                        if p.obj.get_document_type() in types or not types))

    def _get_available_types(self):
        return list(set(p.obj.get_document_type()
                        for p in self.plugins.values()))

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

    def _validate_offset(self, offset):
        try:
            offset = int(offset)
        except ValueError:
            msg = _("offset param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if offset < 0:
            msg = _("offset param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return offset

    def _validate_limit(self, limit):
        try:
            limit = int(limit)
        except ValueError:
            msg = _("limit param must be an integer")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if limit < 1:
            msg = _("limit param must be positive")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        return limit

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

    def _get_query(self, context, query, resource_types, all_projects=False):
        is_admin = context.is_admin
        if is_admin and all_projects:
            query_params = {
                'query': {
                    'query': query
                }
            }
        else:
            filtered_query_list = []
            for resource_type, plugin in six.iteritems(self.plugins):
                try:
                    rbac_filter = plugin.obj.get_rbac_filter(context)
                except Exception as e:
                    msg = _("Error processing %s RBAC filter") % resource_type
                    LOG.error(_LE("Failed to retrieve RBAC filters "
                                  "from search plugin "
                                  "%(ext)s: %(e)s") %
                              {'ext': plugin.name, 'e': e})
                    raise webob.exc.HTTPInternalServerError(explanation=msg)

                if resource_type in resource_types:
                    filter_query = {
                        "query": query,
                        "filter": rbac_filter
                    }
                    filtered_query = {
                        'filtered': filter_query
                    }
                    filtered_query_list.append(filtered_query)

            query_params = {
                'query': {
                    'query': {
                        "bool": {
                            "should": filtered_query_list
                        },
                    }
                }
            }

        return query_params

    def _get_sort_order(self, sort_order):
        if isinstance(sort_order, (six.text_type, dict)):
            # Elasticsearch expects a list
            sort_order = [sort_order]
        elif not isinstance(sort_order, list):
            msg = _("'sort' must be a string, dict or list")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        def replace_sort_field(sort_field):
            # Make some alterations for fields that have a 'raw' field so
            # that documents aren't sorted by tokenized values
            if isinstance(sort_field, six.text_type):
                # Raw field name
                if sort_field in searchlight.elasticsearch.RAW_SORT_FIELDS:
                    return sort_field + ".raw"
            elif isinstance(sort_field, dict):
                for field_name, sort_params in six.iteritems(sort_field):
                    if field_name in searchlight.elasticsearch.RAW_SORT_FIELDS:
                        # There should only be one object
                        return {field_name + ".raw": sort_params}
            else:
                msg = "Unhandled sort type replacing '%s'" % sort_field
                raise webob.exc.HTTPInternalServerError(explanation=msg)
            return sort_field

        return [replace_sort_field(f) for f in sort_order]

    def search(self, request):
        body = self._get_request_body(request)
        self._check_allowed(body)
        query = body.pop('query', {"match_all": {}})
        indices = body.pop('index', None)
        types = body.pop('type', None)
        _source = body.pop('_source', None)
        offset = body.pop('offset', None)
        limit = body.pop('limit', None)
        highlight = body.pop('highlight', None)
        sort_order = body.pop('sort', None)
        # all_projects will determine whether an admin sees
        # filtered results or not
        all_projects = body.pop('all_projects', False)

        available_types = self._get_available_types()
        if not types:
            types = available_types
        else:
            types = [types] if not isinstance(types, list) else types
            for requested_type in types:
                if requested_type not in available_types:
                    msg = _("Resource type '%s' is not in the list of enabled "
                            "plugins") % requested_type
                    raise webob.exc.HTTPBadRequest(explanation=msg)

        available_indices = self._get_available_indices(types)
        if not indices:
            indices = available_indices
        else:
            indices = [indices] if not isinstance(indices, list) else indices
            for requested_index in indices:
                if requested_index not in available_indices:
                    msg = _("Index '%s' is not in the list of enabled "
                            "plugins") % requested_index
                    raise webob.exc.HTTPBadRequest(explanation=msg)

        if not isinstance(types, (list, tuple)):
            types = [types]
        if not isinstance(indices, (list, tuple)):
            indices = [indices]

        query_params = self._get_query(request.context, query, types,
                                       all_projects=all_projects)

        # Apply an additional restriction to elasticsearch to speed things up
        # in addition to the RBAC filters
        query_params['index'] = indices
        query_params['doc_type'] = types

        if _source is not None:
            if isinstance(_source, dict):
                if 'include' in _source:
                    query_params['_source_include'] = _source['include']
                if 'exclude' in _source:
                    query_params['_source_exclude'] = _source['exclude']
            elif isinstance(_source, (list, six.text_type)):
                query_params['_source'] = _source
            else:
                msg = _("'_source' must be a string, dict or list")
                raise webob.exc.HTTPBadRequest(explanation=msg)

        if offset is not None:
            query_params['offset'] = self._validate_offset(offset)

        if limit is not None:
            query_params['limit'] = self._validate_limit(limit)

        if highlight is not None:
            query_params['query']['highlight'] = highlight

        if sort_order is not None:
            query_params['query']['sort'] = self._get_sort_order(sort_order)

        return query_params

    def facets(self, request):
        all_projects = request.params.get('all_projects', 'false')
        query_params = {
            'index_name': request.params.get('index', None),
            'doc_type': request.params.get('type', None),
            'all_projects': all_projects.lower() == 'true',
            'limit_terms': int(request.params.get('limit_terms', 0))
        }
        return query_params


class ResponseSerializer(wsgi.JSONResponseSerializer):
    def __init__(self, schema=None):
        super(ResponseSerializer, self).__init__()
        self.schema = schema

    def search(self, response, query_result):
        body = json.dumps(query_result, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def plugins_info(self, response, query_result):
        body = json.dumps(query_result, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'

    def facets(self, response, query_result):
        body = json.dumps(query_result, ensure_ascii=False)
        response.unicode_body = six.text_type(body)
        response.content_type = 'application/json'


def create_resource():
    """Search resource factory method"""
    plugins = utils.get_search_plugins()
    deserializer = RequestDeserializer(plugins)
    serializer = ResponseSerializer()
    controller = SearchController(plugins)
    return wsgi.Resource(controller, deserializer, serializer)
