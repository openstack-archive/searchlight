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

from elasticsearch import exceptions as es_exc
import operator
from oslo_serialization import jsonutils
from unittest import mock
import webob.exc

from searchlight.api.v1 import search
from searchlight.common import exception
from searchlight.common import utils
import searchlight.elasticsearch
import searchlight.gateway
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


def _action_fixture(op_type, data, index=None, doc_type=None, _id=None,
                    **kwargs):
    action = {
        'action': op_type,
        'id': _id,
        'index': index,
        'type': doc_type,
        'data': data,
    }
    if kwargs:
        action.update(kwargs)

    return action


def _image_fixture(op_type, _id=None, index='searchlight-search',
                   doc_type='OS::Glance::Image',
                   data=None, **kwargs):
    image_data = {
        'name': 'image-1',
        'disk_format': 'raw',
    }
    if data is not None:
        image_data.update(data)

    return _action_fixture(op_type, image_data, index, doc_type, _id, **kwargs)


# To avoid repeating these in all the mocks
REPO_SEARCH = 'searchlight.elasticsearch.CatalogSearchRepo.search'
REPO_PLUGINS = 'searchlight.elasticsearch.CatalogSearchRepo.plugins_info'


class TestControllerSearch(test_utils.BaseTestCase):

    def setUp(self):
        super(TestControllerSearch, self).setUp()
        self.search_controller = search.SearchController()

    def test_search_all(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch.object(self.search_controller, 'search',
                               return_value={}) as mock_search:
            query = {"match_all": {}}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10
            self.search_controller.search(
                request, query, index_name, doc_type, offset, limit)
            mock_search.assert_called_once_with(
                request, query, index_name, doc_type, offset, limit)

    def test_search_all_repo(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, return_value={}) as mock_search:
            query = {"match_all": {}}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10
            self.search_controller.search(
                request, query, index_name, doc_type, offset, limit)
            mock_search.assert_called_once_with(
                index_name, doc_type, query, offset,
                limit, ignore_unavailable=True)

    def test_search_forbidden(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, side_effect=exception.Forbidden):
            query = {"match_all": {}}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10

            self.assertRaises(
                webob.exc.HTTPForbidden, self.search_controller.search,
                request, query, index_name, doc_type, offset, limit)

    def test_search_not_found(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, side_effect=exception.NotFound):
            query = {"match_all": {}}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10

            self.assertRaises(
                webob.exc.HTTPNotFound, self.search_controller.search, request,
                query, index_name, doc_type, offset, limit)

    def test_search_duplicate(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, side_effect=exception.Duplicate):
            query = {"match_all": {}}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10

            self.assertRaises(
                webob.exc.HTTPConflict, self.search_controller.search, request,
                query, index_name, doc_type, offset, limit)

    def test_search_badrequest(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, side_effect=es_exc.RequestError):
            query = {}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10

            self.assertRaises(
                webob.exc.HTTPBadRequest, self.search_controller.search,
                request, query, index_name, doc_type, offset, limit)

    def test_search_internal_server_error(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, side_effect=Exception):
            query = {"match_all": {}}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10

            self.assertRaises(
                webob.exc.HTTPInternalServerError,
                self.search_controller.search,
                request, query, index_name, doc_type, offset, limit)

    @mock.patch(REPO_SEARCH, return_value={})
    def test_search_policy_check(self, _):
        request = unit_test_utils.get_fake_request()
        with mock.patch.object(self.search_controller.policy,
                               'enforce') as mock_enforce:

            self.search_controller.search(request, query={"match_all": {}})
            mock_enforce.assert_called_with(request.context,
                                            'search:query',
                                            request.context.policy_target)

    def test_search_version(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, return_value={}) as mock_search:
            query = {"match_all": {}}
            index_name = "searchlight"
            doc_type = "OS::Glance::Metadef"
            offset = 0
            limit = 10
            self.search_controller.search(
                request, query, index_name, doc_type, offset, limit,
                version=True)
            mock_search.assert_called_once_with(
                index_name, doc_type, query, offset,
                limit, ignore_unavailable=True, version=True)

    def test_search_aggregations(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_SEARCH, return_value={}) as mock_search:
            query = {"query": {"match_all": {}},
                     "aggs": {"test": {"terms": {"field": "some_field"}}}}
            index_name = "searchlight"
            limit = 10
            offset = 0
            doc_type = "OS::Glance::Image"

            self.search_controller.search(
                request, query, index_name, doc_type, offset, limit,
                version=True)

            mock_search.assert_called_once_with(
                index_name, doc_type, query, offset,
                limit, ignore_unavailable=True, version=True)


class TestControllerPluginsInfo(test_utils.BaseTestCase):

    def setUp(self):
        super(TestControllerPluginsInfo, self).setUp()
        self.search_controller = search.SearchController()

    def test_plugins_info_forbidden(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_PLUGINS, side_effect=exception.Forbidden):
            self.assertRaises(
                webob.exc.HTTPForbidden, self.search_controller.plugins_info,
                request, [])

    def test_plugins_info_not_found(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_PLUGINS, side_effect=exception.NotFound):
            self.assertRaises(webob.exc.HTTPNotFound,
                              self.search_controller.plugins_info, request, [])

    def test_plugins_info_internal_server_error(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_PLUGINS, side_effect=Exception):
            self.assertRaises(webob.exc.HTTPInternalServerError,
                              self.search_controller.plugins_info, request, [])

    def test_plugins_info(self):
        request = unit_test_utils.get_fake_request()
        expected = {
            "plugins": [
                {
                    "alias-searching": "searchlight-search",
                    "alias-indexing": "searchlight-listener",
                    "type": "OS::Designate::RecordSet",
                },
                {
                    "alias-searching": "searchlight-search",
                    "alias-indexing": "searchlight-listener",
                    "type": "OS::Designate::Zone",
                },
                {
                    "alias-searching": "searchlight-search",
                    "alias-indexing": "searchlight-listener",
                    "type": "OS::Glance::Image",
                },
                {
                    "alias-searching": "searchlight-search",
                    "alias-indexing": "searchlight-listener",
                    "type": "OS::Glance::Metadef",
                },
                {
                    "alias-searching": "searchlight-search",
                    "alias-indexing": "searchlight-listener",
                    "type": "OS::Nova::Server",
                }
            ]
        }

        # Simulate policy filtering
        doc_types = [p['type'] for p in expected['plugins']]
        actual = self.search_controller.plugins_info(request, doc_types)
        self.assertEqual(['plugins'], list(actual.keys()))

        self.assertEqual(
            sorted(expected['plugins'], key=operator.itemgetter('type')),
            sorted(actual['plugins'], key=operator.itemgetter('type')))


class TestControllerFacets(test_utils.BaseTestCase):
    def setUp(self):
        super(TestControllerFacets, self).setUp()
        self.search_controller = search.SearchController()

    def test_facets(self):
        request = unit_test_utils.get_fake_request()
        doc_types = ["OS::Glance::Image", "OS::Nova::Server"]
        gf_path = 'searchlight.elasticsearch.plugins.base.IndexBase.get_facets'
        with mock.patch(gf_path) as mock_facets:
            mock_facets.return_value = [{"name": "fake", "type": "string"}], 0

            default_response = self.search_controller.facets(
                request, doc_type=doc_types)

            expected = {
                "OS::Nova::Server": {
                    "doc_count": 0,
                    "facets": [{"name": "fake", "type": "string"}]
                },
                "OS::Glance::Image": {
                    "doc_count": 0,
                    "facets": [{"name": "fake", "type": "string"}]
                }
            }
            self.assertEqual(expected, default_response)

            totals_only_response = self.search_controller.facets(
                request, doc_type=doc_types, include_fields=False)

            expected = {"OS::Nova::Server": {"doc_count": 0},
                        "OS::Glance::Image": {"doc_count": 0}}
            self.assertEqual(expected, totals_only_response)


class TestSearchDeserializer(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSearchDeserializer, self).setUp()
        self.deserializer = search.RequestDeserializer(
            utils.get_search_plugins()
        )

    def test_single_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': 'searchlight-search',
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight-search'], output['index'])

    def test_single_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': 'OS::Glance::Image',
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight-search'], output['index'])
        self.assertEqual(['OS::Glance::Image'], output['doc_type'])

    def test_empty_request(self):
        """Tests that ALL registered resource types are searched"""
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({}).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight-search'], output['index'])

        types = [
            'OS::Designate::RecordSet',
            'OS::Designate::Zone',
            'OS::Glance::Image',
            'OS::Glance::Metadef',
            'OS::Ironic::Chassis',
            'OS::Ironic::Node',
            'OS::Ironic::Port',
            'OS::Nova::Flavor',
            'OS::Nova::Server',
            'OS::Nova::ServerGroup',
            'OS::Nova::Hypervisor',
            'OS::Neutron::FloatingIP',
            'OS::Neutron::Net',
            'OS::Neutron::Port',
            'OS::Neutron::Subnet',
            'OS::Neutron::Router',
            'OS::Neutron::SecurityGroup',
            'OS::Cinder::Volume',
            'OS::Cinder::Snapshot'
        ]

        self.assertEqual(['searchlight-search'], output['index'])
        self.assertEqual(sorted(types), sorted(output['doc_type']))

    def test_forbidden_schema(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'schema': {},
        }).encode("latin-1")

        self.assertRaises(webob.exc.HTTPForbidden, self.deserializer.search,
                          request)

    def test_forbidden_self(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'self': {},
        }).encode("latin-1")

        self.assertRaises(webob.exc.HTTPForbidden, self.deserializer.search,
                          request)

    def test_fields_restriction(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': ['description'],
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight-search'], output['index'])
        self.assertEqual(['OS::Glance::Metadef'], output['doc_type'])
        self.assertEqual(['description'], output['_source_include'])

    def test_fields_include_exclude(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': {
                'include': ['some', 'thing.*'],
                'exclude': ['other.*', 'thing']
            }
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertNotIn('_source', output)
        self.assertEqual(['some', 'thing.*'], output['_source_include'])
        # Don't test the role filter exclusion here
        self.assertLessEqual(set(['other.*', 'thing']),
                             set(output['_source_exclude']))

    def test_fields_exclude_rbac(self):
        """Test various forms for source_exclude"""
        role_field = searchlight.elasticsearch.ROLE_USER_FIELD
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': {
                'exclude': ['something', 'other thing']
            }
        }).encode("latin-1")
        output = self.deserializer.search(request)
        self.assertEqual([role_field, 'something', 'other thing'],
                         output['_source_exclude'])

        # Test with a single field
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': {
                'exclude': "something"
            }
        }).encode("latin-1")
        output = self.deserializer.search(request)
        self.assertEqual([role_field, 'something'],
                         output['_source_exclude'])

        # Test with a single field
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': "includeme"
        }).encode("latin-1")
        output = self.deserializer.search(request)
        self.assertEqual([role_field],
                         output['_source_exclude'])
        self.assertEqual("includeme",
                         output['_source_include'])

        # Test with a single field
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': ["includeme", "andme"]
        }).encode("latin-1")
        output = self.deserializer.search(request)
        self.assertEqual([role_field],
                         output['_source_exclude'])
        self.assertEqual(["includeme", "andme"],
                         output['_source_include'])

    def test_bad_field_include(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': 1234,
        }).encode("latin-1")

        self.assertRaisesRegex(
            webob.exc.HTTPBadRequest,
            "'_source' must be a string, dict or list",
            self.deserializer.search,
            request)

    def test_highlight_fields(self):
        """Test that if no highlight_query is given for a field the query is
        applied, and that highlight terms make it through the deserializer.
        """
        request = unit_test_utils.get_fake_request()

        highlight_query = {'query_string': {'query': 'gimme everything'}}

        # Apply highlighting to 'name' explicitly setting require_field_match
        # and 'content' explicitly setting a highlight_query
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'highlight': {
                'fields': {
                    'name': {'require_field_match': True},
                    'content': {
                        'highlight_query': highlight_query
                    }
                }
            }
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight-search'], output['index'])
        self.assertEqual(['OS::Glance::Metadef'], output['doc_type'])

        expected_highlight = {
            'fields': {
                'name': {
                    # Expects the match_all query we passed in, but preserve
                    # require_field_match
                    'highlight_query': {'match_all': {}},
                    'require_field_match': True
                },
                'content': {
                    # Expect the overridden highlight_query and default
                    # require_field_match
                    'highlight_query': highlight_query,
                    'require_field_match': False
                }
            }
        }
        self.assertEqual(expected_highlight, output['query']['highlight'])

    def test_invalid_limit(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'limit': 'invalid',
        }).encode("latin-1")

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_negative_limit(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'limit': -1,
        }).encode("latin-1")

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_invalid_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'offset': 'invalid',
        }).encode("latin-1")

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_negative_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'offset': -1,
        }).encode("latin-1")

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_offset_from_error(self):
        """Test that providing offset and from cause errors"""
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'offset': 10,
            'from': 10
        }).encode("latin-1")
        self.assertRaisesRegex(
            webob.exc.HTTPBadRequest,
            "Provide 'offset' or 'from', but not both",
            self.deserializer.search, request)

    def test_limit_size_error(self):
        """Test that providing limit and size cause errors"""
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'size': 10,
            'limit': 10
        }).encode("latin-1")
        self.assertRaisesRegex(
            webob.exc.HTTPBadRequest,
            "Provide 'limit' or 'size', but not both",
            self.deserializer.search, request)

    def test_limit_and_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'limit': 1,
            'offset': 2,
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(1, output['size'])
        self.assertEqual(2, output['from_'])

    def test_from_and_size(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'size': 1,
            'from': 2,
        }).encode("latin-1")
        output = self.deserializer.search(request)
        self.assertEqual(1, output['size'])
        self.assertEqual(2, output['from_'])

    def test_single_sort(self):
        """Test that a single sort field is correctly transformed"""
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': 'status'
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(['status'], output['query']['sort'])

    def test_single_sort_dir(self):
        """Test that a single sort field & dir is correctly transformed"""
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': {'status': 'desc'}
        }).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual([{'status': 'desc'}], output['query']['sort'])

    def test_multiple_sort(self):
        """Test multiple sort fields"""
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': [
                'status',
                {'created_at': 'desc'},
                {'members': {'order': 'asc', 'mode': 'max'}}
            ]
        }).encode("latin-1")

        output = self.deserializer.search(request)
        expected = [
            'status',
            {'created_at': 'desc'},
            {'members': {'order': 'asc', 'mode': 'max'}}
        ]
        self.assertEqual(expected, output['query']['sort'])

    def test_raw_field_sort(self):
        """Some fields (like name) are treated separately"""
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': [
                'name',
                {'name': {'order': 'desc'}}
            ]
        }).encode("latin-1")

        output = self.deserializer.search(request)
        expected = [
            'name.raw',
            {'name.raw': {'order': 'desc'}}
        ]
        self.assertEqual(expected, output['query']['sort'])

    def test_bad_sort(self):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'index': ['glance'],
            'type': ['OS::Glance::Image'],
            'query': {'match_all': {}},
            'sort': 1234
        }).encode("latin-1")

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    @mock.patch('searchlight.elasticsearch.plugins.nova.servers.' +
                'ServerIndex.get_query_filters')
    def test_rbac_exception(self, mock_query_filters):
        request = unit_test_utils.get_fake_request()
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
        }).encode("latin-1")

        mock_query_filters.side_effect = Exception("Bad RBAC")

        self.assertRaisesRegex(
            webob.exc.HTTPInternalServerError,
            "Error processing OS::Nova::Server RBAC filter",
            self.deserializer.search,
            request)

    def test_rbac_non_admin(self):
        """Test that a non-admin request results in an RBACed query"""
        request = unit_test_utils.get_fake_request(is_admin=False)
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'type': 'OS::Nova::Server',
        }).encode("latin-1")
        output = self.deserializer.search(request)
        tenant_id = '6838eb7b-6ded-dead-beef-b344c77fe8df'

        nova_rbac_filter = {
            'indices': {
                'query': {
                    'bool': {
                        'filter': {
                            'bool': {
                                'must': {
                                    'type': {'value': 'OS::Nova::Server'}
                                },
                                'should': [
                                    {'term': {'tenant_id': tenant_id}}
                                ],
                                'minimum_should_match': 1
                            }
                        }
                    }
                },
                'index': 'searchlight-search',
                'no_match_query': 'none'
            }
        }

        role_field = searchlight.elasticsearch.ROLE_USER_FIELD
        expected_query = {
            'query': {
                'bool': {
                    'filter': {
                        'bool': {
                            'must': {'term': {role_field: 'user'}},
                            'should': [nova_rbac_filter],
                            'minimum_should_match': 1
                        }
                    },
                    'must': {'match_all': {}}
                }
            }
        }
        self.assertEqual(expected_query, output['query'])

    def test_rbac_admin(self):
        """Test that admins have RBAC applied"""
        request = unit_test_utils.get_fake_request(is_admin=True)
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'type': 'OS::Nova::Server',
        }).encode("latin-1")
        output = self.deserializer.search(request)
        tenant_id = '6838eb7b-6ded-dead-beef-b344c77fe8df'
        nova_rbac_filter = {
            'indices': {
                'query': {
                    'bool': {
                        'filter': {
                            'bool': {
                                'must': {
                                    'type': {'value': 'OS::Nova::Server'}
                                },
                                'should': [
                                    {'term': {'tenant_id': tenant_id}}
                                ],
                                'minimum_should_match': 1
                            }
                        }
                    }
                },
                'index': 'searchlight-search',
                'no_match_query': 'none'
            }
        }

        role_field = searchlight.elasticsearch.ROLE_USER_FIELD
        expected_query = {
            'query': {
                'bool': {
                    'filter': {
                        'bool': {
                            'must': {'term': {role_field: 'admin'}},
                            'should': [nova_rbac_filter],
                            'minimum_should_match': 1
                        }
                    },
                    'must': {'match_all': {}}
                }
            }
        }

        self.assertEqual(expected_query, output['query'])

        # Now test with all_projects
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'type': 'OS::Nova::Server',
            'all_projects': True,
        }).encode("latin-1")

        # Test that if a plugin doesn't allow RBAC to be ignored,
        # it isn't. Do it with mocking, because mocking is best
        with mock.patch('searchlight.elasticsearch.plugins.nova.servers.'
                        'ServerIndex.allow_admin_ignore_rbac',
                        new_callable=mock.PropertyMock) as ignore_mock:
            ignore_mock.return_value = False
            output = self.deserializer.search(request)
            self.assertEqual(expected_query, output['query'])

        # Now test the same under the default allow-ignore-rbac conditions,
        # and we shouldn't see the tenant restrictions
        output = self.deserializer.search(request)

        # No more tenant restriction in the expected result
        nova_index_filter = nova_rbac_filter['indices']['query']['bool']
        del nova_index_filter['filter']['bool']['should']
        del nova_index_filter['filter']['bool']['minimum_should_match']

        self.assertEqual(expected_query, output['query'])

    def test_default_facet_options(self):
        request = unit_test_utils.get_fake_request(path='/v1/search/facets')
        output = self.deserializer.facets(request)

        output['doc_type'] = sorted(output['doc_type'])
        expected_doc_types = sorted(utils.get_search_plugins().keys())
        expected = {'index_name': None, 'doc_type': expected_doc_types,
                    'all_projects': False, 'limit_terms': 0,
                    'include_fields': True, 'exclude_options': False}
        self.assertEqual(expected, output)

    def test_facet_exclude_options(self):
        path = '/v1/search/facets?exclude_options=True'
        request = unit_test_utils.get_fake_request(path=path)
        output = self.deserializer.facets(request)

        output['doc_type'] = sorted(output['doc_type'])
        expected_doc_types = sorted(utils.get_search_plugins().keys())
        expected = {'index_name': None, 'doc_type': expected_doc_types,
                    'all_projects': False, 'limit_terms': 0,
                    'include_fields': True, 'exclude_options': True}
        self.assertEqual(expected, output)

    def test_search_version(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        request.body = jsonutils.dumps({
            'query': {'match_all': {}},
            'version': True
        }).encode("latin-1")
        output = self.deserializer.search(request)
        self.assertEqual(True, output['version'])

    def test_search_aggregations(self):
        request = unit_test_utils.get_fake_request()

        aggs = {'names': {'terms': {'field': 'name'}},
                'max_something': {'max': {'field': 'something'}}}

        # Apply highlighting to 'name' explicitly setting require_field_match
        # and 'content' explicitly setting a highlight_query
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'aggregations': aggs}).encode("latin-1")

        output = self.deserializer.search(request)
        self.assertEqual(aggs, output['query']['aggregations'])

        # Test 'aggs' too
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'aggs': aggs}).encode("latin-1")
        output = self.deserializer.search(request)
        self.assertEqual(aggs, output['query']['aggregations'])

    def test_global_aggregation_not_allowed(self):
        """The 'global' aggregation type bypasses the search query (thus
        bypassing RBAC). This is Bad, so we won't allow it. It can only occur
        as a top level aggregation.
        """
        request = unit_test_utils.get_fake_request()

        aggs = {
            'cheating_rbac': {
                'global': {},
                'aggregations': {'name': {'terms': {'field': 'name'}}}
            }
        }
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'aggregations': aggs}).encode("latin-1")

        self.assertRaises(
            webob.exc.HTTPForbidden, self.deserializer.search,
            request)

    def test_search_aggregations_bad_request(self):
        """Test that 'aggs' AND 'aggregations' can't be specified together"""
        request = unit_test_utils.get_fake_request()

        aggs = {"something": "something"}
        request.body = jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'aggregations': aggs,
            'aggs': aggs}).encode("latin-1")

        self.assertRaisesRegex(
            webob.exc.HTTPBadRequest,
            "A request cannot include both 'aggs' and 'aggregations'",
            self.deserializer.search, request)


class TestResponseSerializer(test_utils.BaseTestCase):
    def setUp(self):
        super(TestResponseSerializer, self).setUp()
        self.serializer = search.ResponseSerializer()

    def test_plugins_info(self):
        expected = {
            'plugins': [
                {
                    'OS::Glance::Image': {
                        'index': 'searchlight-search',
                        'type': 'OS::Glance::Image'
                    }
                },
                {
                    'OS::Glance::Metadef': {
                        'index': 'searchlight-search',
                        'type': 'OS::Glance::Metadef'
                    }
                }
            ]
        }

        request = webob.Request.blank('/v0.1/search')
        response = webob.Response(request=request)
        result = {
            'plugins': [
                {
                    'OS::Glance::Image': {
                        'index': 'searchlight-search',
                        'type': 'OS::Glance::Image'
                    }
                },
                {
                    'OS::Glance::Metadef': {
                        'index': 'searchlight-search',
                        'type': 'OS::Glance::Metadef'
                    }
                }
            ]
        }
        self.serializer.search(response, result)
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)

    def test_search(self):
        expected = [{
            'id': '1',
            'name': 'image-1',
            'disk_format': 'raw',
        }]

        request = webob.Request.blank('/v0.1/search')
        response = webob.Response(request=request)
        result = [{
            'id': '1',
            'name': 'image-1',
            'disk_format': 'raw',
        }]
        self.serializer.search(response, result)
        actual = jsonutils.loads(response.body)
        self.assertEqual(expected, actual)
        self.assertEqual('application/json', response.content_type)
