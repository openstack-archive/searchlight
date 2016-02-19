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
import mock
from oslo_serialization import jsonutils
import six
import webob.exc

from searchlight.api.v1 import search as search
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


def _image_fixture(op_type, _id=None, index='searchlight',
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


class TestControllerPluginsInfo(test_utils.BaseTestCase):

    def setUp(self):
        super(TestControllerPluginsInfo, self).setUp()
        self.search_controller = search.SearchController()

    def test_plugins_info_forbidden(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_PLUGINS, side_effect=exception.Forbidden):
            self.assertRaises(
                webob.exc.HTTPForbidden, self.search_controller.plugins_info,
                request)

    def test_plugins_info_not_found(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_PLUGINS, side_effect=exception.NotFound):
            self.assertRaises(webob.exc.HTTPNotFound,
                              self.search_controller.plugins_info, request)

    def test_plugins_info_internal_server_error(self):
        request = unit_test_utils.get_fake_request()
        with mock.patch(REPO_PLUGINS, side_effect=Exception):
            self.assertRaises(webob.exc.HTTPInternalServerError,
                              self.search_controller.plugins_info, request)

    def test_plugins_info(self):
        request = unit_test_utils.get_fake_request()
        expected = {
            "plugins": [
                {
                    "index": "searchlight",
                    "type": "OS::Designate::RecordSet",
                    "name": "OS::Designate::RecordSet"
                },
                {
                    "index": "searchlight",
                    "type": "OS::Designate::Zone",
                    "name": "OS::Designate::Zone"
                },
                {
                    "index": "searchlight", "type": "OS::Glance::Image",
                    "name": "OS::Glance::Image"
                },
                {
                    "index": "searchlight", "type": "OS::Glance::Metadef",
                    "name": "OS::Glance::Metadef"
                },
                {
                    "index": "searchlight", "type": "OS::Nova::Server",
                    "name": "OS::Nova::Server"
                }
            ]
        }

        actual = self.search_controller.plugins_info(request)
        self.assertEqual(sorted(expected), sorted(actual))


class TestSearchDeserializer(test_utils.BaseTestCase):

    def setUp(self):
        super(TestSearchDeserializer, self).setUp()
        self.deserializer = search.RequestDeserializer(
            utils.get_search_plugins()
        )

    def test_single_index(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'index': 'searchlight',
        }))

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight'], output['index'])

    def test_single_type(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': 'OS::Glance::Image',
        }))

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight'], output['index'])
        self.assertEqual(['OS::Glance::Image'], output['doc_type'])

    def test_empty_request(self):
        """Tests that ALL registered resource types are searched"""
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({}))

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight'], output['index'])

        types = [
            'OS::Designate::RecordSet',
            'OS::Designate::Zone',
            'OS::Glance::Image',
            'OS::Glance::Metadef',
            'OS::Nova::Server',
        ]

        self.assertEqual(['searchlight'], output['index'])
        self.assertEqual(sorted(types), sorted(output['doc_type']))

    def test_forbidden_schema(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'schema': {},
        }))

        self.assertRaises(webob.exc.HTTPForbidden, self.deserializer.search,
                          request)

    def test_forbidden_self(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'self': {},
        }))

        self.assertRaises(webob.exc.HTTPForbidden, self.deserializer.search,
                          request)

    def test_fields_restriction(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': ['description'],
        }))

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight'], output['index'])
        self.assertEqual(['OS::Glance::Metadef'], output['doc_type'])
        self.assertEqual(['description'], output['_source_include'])

    def test_fields_include_exclude(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': {
                'include': ['some', 'thing.*'],
                'exclude': ['other.*', 'thing']
            }
        }))

        output = self.deserializer.search(request)
        self.assertFalse('_source' in output)
        self.assertEqual(['some', 'thing.*'], output['_source_include'])
        # Don't test the role filter exclusion here
        self.assertTrue(set(['other.*', 'thing']) <=
                        set(output['_source_exclude']))

    def test_fields_exclude_rbac(self):
        """Test various forms for source_exclude"""
        role_field = searchlight.elasticsearch.ROLE_USER_FIELD
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': {
                'exclude': ['something', 'other thing']
            }
        }))
        output = self.deserializer.search(request)
        self.assertEqual([role_field, 'something', 'other thing'],
                         output['_source_exclude'])

        # Test with a single field
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': {
                'exclude': "something"
            }
        }))
        output = self.deserializer.search(request)
        self.assertEqual([role_field, 'something'],
                         output['_source_exclude'])

        # Test with a single field
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': "includeme"
        }))
        output = self.deserializer.search(request)
        self.assertEqual([role_field],
                         output['_source_exclude'])
        self.assertEqual("includeme",
                         output['_source_include'])

        # Test with a single field
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': ["includeme", "andme"]
        }))
        output = self.deserializer.search(request)
        self.assertEqual([role_field],
                         output['_source_exclude'])
        self.assertEqual(["includeme", "andme"],
                         output['_source_include'])

    def test_bad_field_include(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            '_source': 1234,
        }))

        self.assertRaisesRegexp(
            webob.exc.HTTPBadRequest,
            "'_source' must be a string, dict or list",
            self.deserializer.search,
            request)

    def test_highlight_fields(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'highlight': {'fields': {'name': {}}}
        }))

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight'], output['index'])
        self.assertEqual(['OS::Glance::Metadef'], output['doc_type'])
        self.assertEqual({'name': {}}, output['query']['highlight']['fields'])

    def test_invalid_limit(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'limit': 'invalid',
        }))

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_negative_limit(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'limit': -1,
        }))

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_invalid_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'offset': 'invalid',
        }))

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_negative_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'offset': -1,
        }))

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    def test_limit_and_offset(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'type': ['OS::Glance::Metadef'],
            'query': {'match_all': {}},
            'limit': 1,
            'offset': 2,
        }))

        output = self.deserializer.search(request)
        self.assertEqual(['searchlight'], output['index'])
        self.assertEqual(['OS::Glance::Metadef'], output['doc_type'])
        self.assertEqual(1, output['limit'])
        self.assertEqual(2, output['offset'])

    def test_single_sort(self):
        """Test that a single sort field is correctly transformed"""
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': 'status'
        }))

        output = self.deserializer.search(request)
        self.assertEqual(['status'], output['query']['sort'])

    def test_single_sort_dir(self):
        """Test that a single sort field & dir is correctly transformed"""
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': {'status': 'desc'}
        }))

        output = self.deserializer.search(request)
        self.assertEqual([{'status': 'desc'}], output['query']['sort'])

    def test_multiple_sort(self):
        """Test multiple sort fields"""
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': [
                'status',
                {'created_at': 'desc'},
                {'members': {'order': 'asc', 'mode': 'max'}}
            ]
        }))

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
        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
            'sort': [
                'name',
                {'name': {'order': 'desc'}}
            ]
        }))

        output = self.deserializer.search(request)
        expected = [
            'name.raw',
            {'name.raw': {'order': 'desc'}}
        ]
        self.assertEqual(expected, output['query']['sort'])

    def test_bad_sort(self):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'index': ['glance'],
            'type': ['OS::Glance::Image'],
            'query': {'match_all': {}},
            'sort': 1234
        }))

        self.assertRaises(webob.exc.HTTPBadRequest, self.deserializer.search,
                          request)

    @mock.patch('searchlight.elasticsearch.plugins.nova.servers.' +
                'ServerIndex.get_rbac_filter')
    def test_rbac_exception(self, mock_rbac_filter):
        request = unit_test_utils.get_fake_request()
        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
        }))

        mock_rbac_filter.side_effect = Exception("Bad RBAC")

        self.assertRaisesRegexp(
            webob.exc.HTTPInternalServerError,
            "Error processing OS::Nova::Server RBAC filter",
            self.deserializer.search,
            request)

    def test_rbac_non_admin(self):
        """Test that a non-admin request results in an RBACed query"""
        request = unit_test_utils.get_fake_request(is_admin=False)
        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
            'type': 'OS::Nova::Server',
        }))
        output = self.deserializer.search(request)

        nova_rbac_filter = {
            'indices': {
                'filter': {
                    'and': [{
                        'term': {
                            'tenant_id': '6838eb7b-6ded-dead-beef-b344c77fe8df'
                        }},
                        {'type': {'value': 'OS::Nova::Server'}}
                    ]},
                'index': 'searchlight',
                'no_match_filter': 'none'
            }
        }

        expected_query = {
            'bool': {
                'should': [{
                    'filtered': {
                        'filter': [nova_rbac_filter],
                        'query': {u'match_all': {}}
                    }
                }]
            }
        }
        output_query = output['query']
        self.assertEqual(expected_query,
                         output_query['query']['filtered']['query'])

    def test_rbac_admin(self):
        """Test that admins have RBAC applied unless 'all_projects' is true"""
        request = unit_test_utils.get_fake_request(is_admin=True)
        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
            'type': 'OS::Nova::Server',
        }))
        output = self.deserializer.search(request)

        nova_rbac_filter = {
            'indices': {
                'filter': {
                    'and': [{
                        'term': {
                            'tenant_id': '6838eb7b-6ded-dead-beef-b344c77fe8df'
                        }},
                        {'type': {'value': 'OS::Nova::Server'}}
                    ]},
                'index': 'searchlight',
                'no_match_filter': 'none'
            }
        }
        expected_query = {
            'bool': {
                'should': [{
                    'filtered': {
                        'filter': [nova_rbac_filter],
                        'query': {u'match_all': {}}
                    }
                }]
            }
        }

        output_query = output['query']
        self.assertEqual(expected_query,
                         output_query['query']['filtered']['query'])

        request.body = six.b(jsonutils.dumps({
            'query': {'match_all': {}},
            'type': 'OS::Nova::Server',
            'all_projects': True,
        }))
        output = self.deserializer.search(request)

        expected_query = {
            'match_all': {}
        }

        output_query = output['query']
        self.assertEqual(expected_query,
                         output_query['query']['filtered']['query'])

    def test_default_facet_options(self):
        request = unit_test_utils.get_fake_request(path='/v1/search/facets')
        output = self.deserializer.facets(request)

        expected = {'index_name': None, 'doc_type': None,
                    'all_projects': False, 'limit_terms': 0}
        self.assertEqual(expected, output)


class TestResponseSerializer(test_utils.BaseTestCase):
    def setUp(self):
        super(TestResponseSerializer, self).setUp()
        self.serializer = search.ResponseSerializer()

    def test_plugins_info(self):
        expected = {
            'plugins': [
                {
                    'OS::Glance::Image': {
                        'index': 'searchlight',
                        'type': 'OS::Glance::Image'
                    }
                },
                {
                    'OS::Glance::Metadef': {
                        'index': 'searchlight',
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
                        'index': 'searchlight',
                        'type': 'OS::Glance::Image'
                    }
                },
                {
                    'OS::Glance::Metadef': {
                        'index': 'searchlight',
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
