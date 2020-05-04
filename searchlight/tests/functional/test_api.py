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

import os
import time
from unittest import mock

from oslo_serialization import jsonutils
from oslo_utils import uuidutils

from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import functional
from searchlight.tests import utils as test_utils

TENANT1 = uuidutils.generate_uuid()
TENANT2 = uuidutils.generate_uuid()
TENANT3 = uuidutils.generate_uuid()

USER1 = uuidutils.generate_uuid()

fake_version_list = [test_utils.FakeVersion('2.1'),
                     test_utils.FakeVersion('2.1')]

nova_version_getter = 'novaclient.v2.client.versions.VersionManager.list'

MATCH_ALL = {"query": {"match_all": {}}, "sort": [{"name": {"order": "asc"}}]}
EMPTY_RESPONSE = {"hits": {"hits": [], "total": 0, "max_score": 0.0},
                  "_shards": {"successful": 0, "failed": 0, "total": 0},
                  "took": 1,
                  "timed_out": False}


class TestSearchApi(functional.FunctionalTest):
    """Test case for API functionality that's not plugin-specific, although
    it can use plugins for the sake of making requests
    """
    def _modify_policy_file(self, rules):
        with open(self.policy_file, 'r+b') as policy_file:
            existing_policy = jsonutils.load(policy_file)

        existing_policy.update(rules)

        with open(self.policy_file, 'w') as policy_file:
            jsonutils.dump(existing_policy, policy_file)

        time.sleep(2)

    def test_server_up(self):
        self.assertTrue(self.ping_server(self.api_port))

    def test_elasticsearch(self):
        """Index a document and check elasticsearch for it to check
        things are working.
        """
        images_plugin = self.initialized_plugins['OS::Glance::Image']
        doc_id = uuidutils.generate_uuid()
        doc = {
            "owner": TENANT1,
            "visibility": "public",
            "id": doc_id,
            "name": "owned by tenant 1",
            "owner": TENANT1,
            "created_at": "2016-04-06T12:48:18Z"
        }

        self._index(images_plugin,
                    [doc])

        doc["project_id"] = doc["owner"]
        # Test the raw elasticsearch response
        es_doc = self._get_elasticsearch_doc(
            images_plugin.alias_name_search,
            images_plugin.get_document_type(),
            doc_id)
        self.assertEqual(set(['admin', 'user']),
                         set(es_doc['_source'].pop(ROLE_USER_FIELD)))

        doc['members'] = []
        doc['image_type'] = 'image'
        self.assertEqual(doc, es_doc['_source'])

    def test_empty_results(self):
        """Test an empty dataset gets empty results."""
        response, json_content = self._search_request(MATCH_ALL, TENANT1)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_nested_objects(self):
        """Test queries against documents with nested complex objects."""
        doc1 = {
            "owner": TENANT1,
            "visibility": "public",
            "objects": [],
            "tags": [],
            "namespace": "some.value1",
            "created_at": "2016-04-06T12:48:18Z",
            "properties": {"prop1": {"title": "hello"},
                           "prop2": {"title": "bye"}}
        }
        doc2 = {
            "owner": TENANT1,
            "visibility": "public",
            "namespace": "some.value2",
            "objects": [],
            "tags": [],
            "created_at": "2016-04-06T12:48:18Z",
            "properties": {"prop1": {"title": "something else"},
                           "prop2": {"title": "hello"}}
        }

        self._index(self.initialized_plugins['OS::Glance::Metadef'],
                    [doc1, doc2])

        # Convert the input docs into expected format
        additional_props = {
            'resource_types': [],
            'display_name': None,
            'description': None,
            'protected': None,
            'updated_at': None,
            'project_id': TENANT1
        }
        doc1.update(additional_props)
        doc2.update(additional_props)

        doc1["properties"] = [{"name": "prop1", "title": "hello"},
                              {"name": "prop2", "title": "bye"}]
        doc2["properties"] = [{"name": "prop1", "title": "something else"},
                              {"name": "prop2", "title": "hello"}]
        doc1["id"] = doc1["namespace"]
        doc1["name"] = doc1["namespace"]
        doc2["id"] = doc2["namespace"]
        doc2["name"] = doc2["namespace"]

        def get_nested(qs):
            return {
                "query": {
                    "nested": {
                        "path": "properties",
                        "query": {
                            "query_string": {"query": qs}
                        }
                    }
                },
                "sort": [{"namespace": {"order": "asc"}}]
            }

        # Expect this to match both documents
        querystring = "properties.name:prop1"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1, doc2], self._get_hit_source(json_content))

        # Expect this to match only doc1
        querystring = "properties.name:prop1 AND properties.title:hello"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1], self._get_hit_source(json_content))

        # Expect this not to match any documents, because it
        # doesn't properly match any nested objects
        querystring = "properties.name:prop1 AND properties.title:bye"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([], self._get_hit_source(json_content))

        # Expect a match with
        querystring = "properties.name:prop3 OR properties.title:bye"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1], self._get_hit_source(json_content))

    def test_query_none(self):
        """Test search when query is not specified"""
        id_1 = uuidutils.generate_uuid()
        tenant1_doc = {
            "owner": TENANT1,
            "id": id_1,
            "visibility": "public",
            "name": "owned by tenant 1",
            "created_at": "2016-04-06T12:48:18Z"
        }

        self._index(self.initialized_plugins['OS::Glance::Image'],
                    [tenant1_doc])

        response, json_content = self._search_request({"all_projects": True},
                                                      TENANT1)
        self.assertEqual(200, response.status_code)
        tenant1_doc["members"] = []
        tenant1_doc["project_id"] = tenant1_doc["owner"]
        self.assertEqual([tenant1_doc], self._get_hit_source(json_content))

    def test_facet_exclude_fields(self):
        id_1 = uuidutils.generate_uuid()
        tenant1_doc = {
            "owner": TENANT1,
            "id": id_1,
            "visibility": "public",
            "name": "owned by tenant 1",
            "created_at": "2016-04-06T12:48:18Z"
        }

        self._index(self.initialized_plugins['OS::Glance::Image'],
                    [tenant1_doc])

        response, json_content = self._facet_request(
            TENANT1,
            include_fields=False,
            doc_type="OS::Nova::Server")
        self.assertEqual(200, response.status_code)
        self.assertEqual(set(["doc_count"]),
                         set(json_content["OS::Nova::Server"].keys()))
        self.assertEqual(0, json_content["OS::Nova::Server"]["doc_count"])

        response, json_content = self._facet_request(
            TENANT1,
            include_fields=False,
            doc_type="OS::Glance::Image")
        self.assertEqual(1, json_content["OS::Glance::Image"]["doc_count"])

    def test_facet_rbac(self):
        tenant1_doc = {
            "owner": TENANT1,
            "id": uuidutils.generate_uuid(),
            "visibility": "private",
            "name": "owned by tenant 1",
            "container_format": "not-shown",
            "created_at": "2016-04-06T12:48:18Z"
        }
        tenant2_doc = {
            "owner": TENANT2,
            "id": uuidutils.generate_uuid(),
            "visibility": "private",
            "name": "owned by tenant 1",
            "container_format": "shown",
            "created_at": "2016-04-06T12:48:18Z"
        }
        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        return_value=[]):
            self._index(self.initialized_plugins['OS::Glance::Image'],
                        [tenant1_doc, tenant2_doc])

        response, json_content = self._facet_request(
            TENANT1,
            include_fields=True,
            doc_type="OS::Glance::Image")
        self.assertEqual(1, json_content["OS::Glance::Image"]["doc_count"])
        facets = json_content["OS::Glance::Image"]["facets"]
        visibility_facet = list(filter(lambda f: f["name"] == "visibility",
                                       facets))[0]
        self.assertEqual([{"key": "private", "doc_count": 1}],
                         visibility_facet["options"])

    def test_facets(self):
        """Check facets for a non-nested field (status)"""
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        server1 = {
            u'addresses': {},
            u'flavor': {u'id': u'1'},
            u'id': u'6c41b4d1-f0fa-42d6-9d8d-e3b99695aa69',
            u'image': {u'id': u'a'},
            u'name': u'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'created_at': u'2016-04-06T12:48:18Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }
        server2 = {
            u'addresses': {},
            u'flavor': {u'id': u'1'},
            u'id': u'08ca6c43-eea8-48d0-bbb2-30c50109d5d8',
            u'image': {u'id': u'a'},
            u'name': u'instance2',
            u'status': u'RESUMING',
            u'tenant_id': TENANT1,
            u'created_at': u'2016-04-06T12:48:18Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }
        server3 = {
            u'addresses': {},
            u'flavor': {u'id': u'1'},
            u'id': u'08ca6c43-f0fa-48d0-48d0-53453522cda4',
            u'image': {u'id': u'a'},
            u'name': u'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'created_at': u'2016-04-06T12:48:18Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }
        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(
                servers_plugin,
                [test_utils.DictObj(**server1),
                 test_utils.DictObj(**server2),
                 test_utils.DictObj(**server3)])

        # Query facets with options.
        response, json_content = self._facet_request(
            TENANT1,
            doc_type="OS::Nova::Server")

        self.assertEqual(3, json_content['OS::Nova::Server']['doc_count'])

        expected = {
            u'name': u'status',
            u'options': [
                {u'doc_count': 2, u'key': u'active'},
                {u'doc_count': 1, u'key': u'resuming'},
            ],
            u'type': u'string'
        }

        status_facet = list(filter(
            lambda f: f['name'] == 'status',
            json_content['OS::Nova::Server']['facets']
        ))[0]
        self.assertEqual(
            expected,
            status_facet,
        )

        # Query facets without options.
        response, json_content = self._facet_request(
            TENANT1,
            doc_type="OS::Nova::Server", exclude_options=True)

        self.assertEqual(3, json_content['OS::Nova::Server']['doc_count'])

        expected = {
            u'name': u'status',
            u'type': u'string'
        }

        status_facet = list(filter(
            lambda f: f['name'] == 'status',
            json_content['OS::Nova::Server']['facets']
        ))[0]
        self.assertEqual(
            expected,
            status_facet,
        )

    def test_search_rbac(self):
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        server1 = {
            u'addresses': {},
            u'flavor': {u'id': u'1'},
            u'id': u'6c41b4d1-f0fa-42d6-9d8d-e3b99695aa69',
            u'image': {u'id': u'a'},
            u'name': u'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'created_at': u'2016-04-06T12:48:18Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }
        server2 = {
            u'addresses': {},
            u'flavor': {u'id': u'1'},
            u'id': u'08ca6c43-eea8-48d0-bbb2-30c50109d5d8',
            u'image': {u'id': u'a'},
            u'name': u'instance2',
            u'status': u'RESUMING',
            u'tenant_id': TENANT2,
            u'created_at': u'2016-04-06T12:48:18Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }

        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(
                servers_plugin,
                [test_utils.DictObj(**server1),
                 test_utils.DictObj(**server2)])

        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Nova::Server"},
            TENANT1,
            role="member")
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual(["6c41b4d1-f0fa-42d6-9d8d-e3b99695aa69"],
                         [h["_source"]["id"]
                          for h in json_content["hits"]["hits"]])

        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Nova::Server",
             "all_projects": True},
            TENANT1,
            role="admin")
        self.assertEqual(2, json_content['hits']['total'])

    def test_nested_facets(self):
        """Check facets for a nested field (networks.OS-EXT-IPS:type). We
        expect a single count per server matched, not per object in the
        'networks' field. Also check that for fields that are typed as
        'object' (not 'nested') they're marked appropriately
        """
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        server1 = {
            u'addresses': {
                u'net4': [
                    {u'addr': u'127.0.0.1',
                     u'OS-EXT-IPS:type': u'fixed',
                     u'version': 4},
                    {u'addr': u'127.0.0.1',
                     u'OS-EXT-IPS:type': u'fixed',
                     u'version': 4}
                ]
            },
            u'flavor': {u'id': u'1'},
            u'id': u'6c41b4d1-f0fa-42d6-9d8d-e3b99695aa69',
            u'image': {u'id': u'a'},
            u'name': u'instance1',
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }

        server2 = {
            u'addresses': {
                u'net4': [
                    {u'addr': u'127.0.0.1',
                     u'OS-EXT-IPS:type': u'fixed',
                     u'version': 4},
                    {u'addr': u'127.0.0.1',
                     u'OS-EXT-IPS:type': u'floating',
                     u'version': 4}
                ]
            },
            u'flavor': {u'id': u'1'},
            u'id': u'08ca6c43-eea8-48d0-bbb2-30c50109d5d8',
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
            u'image': {u'id': u'a'},
            u'name': u'instance2',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }

        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(
                servers_plugin,
                [test_utils.DictObj(**server1),
                 test_utils.DictObj(**server2)])

        response, json_content = self._facet_request(
            TENANT1,
            doc_type="OS::Nova::Server")

        self.assertEqual(2, json_content['OS::Nova::Server']['doc_count'])

        self.assertEqual(['OS::Nova::Server'],
                         list(json_content.keys()))

        # server1 has two fixed addresses (which should be rolled up into one
        # match). server2 has fixed and floating addresses.
        expected = {
            u'name': u'networks.OS-EXT-IPS:type',
            u'options': [
                {u'doc_count': 2, u'key': u'fixed'},
                {u'doc_count': 1, u'key': u'floating'},
            ],
            u'type': u'string',
            u'nested': True
        }
        fixed_network_facet = list(filter(
            lambda f: f['name'] == 'networks.OS-EXT-IPS:type',
            json_content['OS::Nova::Server']['facets']
        ))[0]
        self.assertEqual(
            expected,
            fixed_network_facet,
        )

        # Check that 'image.id' (not nested but 'object') has nested=False
        expected = {
            u'name': u'image.id',
            u'type': u'string',
            u'nested': False,
            u'resource_type': u'OS::Glance::Image',
            u'options': [
                {u'doc_count': 2, u'key': u'a'}
            ]
        }
        image_facet = list(filter(
            lambda f: f['name'] == 'image.id',
            json_content['OS::Nova::Server']['facets']
        ))[0]
        self.assertEqual(
            expected,
            image_facet,
        )

    def test_server_role_field_rbac(self):
        """Check that admins and users get different versions of documents"""
        doc_id = u'abc'
        s1 = {
            u'addresses': {},
            u'OS-DCF:diskConfig': u'MANUAL',
            u'OS-EXT-AZ:availability_zone': u'nova',
            u'OS-EXT-SRV-ATTR:host': u'devstack',
            u'OS-EXT-SRV-ATTR:hypervisor_hostname': u'devstack',
            u'OS-EXT-SRV-ATTR:instance_name': u'instance-00000001',
            u'id': doc_id,
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
        }

        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(
                servers_plugin,
                [test_utils.DictObj(**s1)])

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(json_content['hits']['hits']))
        hit = json_content['hits']['hits'][0]
        self.assertEqual(doc_id + "_ADMIN", hit['_id'])
        for k in ('OS-EXT-SRV-ATTR:host',
                  'OS-EXT-SRV-ATTR:hypervisor_hostname',
                  'OS-EXT-SRV-ATTR:instance_name'):
            self.assertIn(k, hit['_source'])

        # Now as a non admin
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="member")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(json_content['hits']['hits']))
        hit = json_content['hits']['hits'][0]
        self.assertEqual(doc_id + "_USER", hit['_id'])
        for k, v in hit.items():
            self.assertFalse(k.startswith('OS-EXT-SRV-ATTR:'),
                             'No protected attributes should be present')

        for field in (u'status', u'OS-DCF:diskConfig'):
            self.assertIn(field, hit['_source'])

    def test_role_fishing(self):
        """Run some searches to ward against 'fishing' type attacks such that
        'admin only' fields can't be searched by ordinary users
        """
        admin_field, admin_value = (u'OS-EXT-SRV-ATTR:host', u'devstack')

        doc_id = u'abc'
        s1 = {
            u'addresses': {},
            u'id': doc_id,
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            admin_field: admin_value,
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z',
        }

        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(
                servers_plugin,
                [test_utils.DictObj(**s1)])

        # For each of these queries (which are really looking for the same
        # thing) we expect a result for an admin, and no result for a user
        term_query = {'term': {admin_field: admin_value}}
        query_string = {'query_string': {'query': admin_value}}  # search 'all'
        query_string_field = {'query_string': {
            'default_field': admin_field, 'query': admin_value}}

        for query in (term_query, query_string, query_string_field):
            full_query = {'query': query}
            response, json_content = self._search_request(full_query,
                                                          TENANT1,
                                                          role="admin")
            self.assertEqual(200, response.status_code)
            self.assertEqual(1, json_content['hits']['total'],
                             "No results for: %s" % query)
            self.assertEqual(doc_id + '_ADMIN',
                             json_content['hits']['hits'][0]['_id'])

            # The same search should not work for users
            response, json_content = self._search_request(full_query,
                                                          TENANT1,
                                                          role="user")
            self.assertEqual(200, response.status_code)
            self.assertEqual(0, json_content['hits']['total'])

        # Run the same queries against 'name'; should get results
        term_query['term'] = {'name': 'instance1'}
        query_string['query_string']['query'] = 'instance1'
        query_string_field['query_string'] = {
            'default_field': 'name', 'query': 'instance1'
        }

        for query in (term_query, query_string, query_string_field):
            full_query = {'query': query}
            response, json_content = self._search_request(full_query,
                                                          TENANT1,
                                                          role="user")
            self.assertEqual(200, response.status_code)
            self.assertEqual(1, json_content['hits']['total'],
                             "No results for: %s %s" % (query, json_content))
            self.assertEqual(doc_id + '_USER',
                             json_content['hits']['hits'][0]['_id'])

    def test_resource_policy(self):
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        images_plugin = self.initialized_plugins['OS::Glance::Image']
        server_doc = {
            u'addresses': {},
            u'id': 'abcdef',
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z'
        }

        image_doc = {
            "owner": TENANT1,
            "id": "1234567890",
            "visibility": "public",
            "name": "image",
            "created_at": "2016-04-06T12:48:18Z"
        }

        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(servers_plugin, [test_utils.DictObj(**server_doc)])
        self._index(images_plugin, [image_doc])

        # Modify the policy file to restrict Nova servers
        self._modify_policy_file({"resource:OS::Nova::Server": "role:admin"})

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="user")
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual('OS::Glance::Image',
                         json_content['hits']['hits'][0]['_type'])

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual(2, json_content['hits']['total'])
        self.assertEqual(set(['OS::Glance::Image', 'OS::Nova::Server']),
                         set([hit['_type']
                              for hit in json_content['hits']['hits']]))

        response, json_content = self._facet_request(TENANT1, role="user")
        self.assertNotIn('OS::Nova::Server', json_content)

        response, json_content = self._facet_request(TENANT1, role="admin")
        self.assertIn('OS::Nova::Server', json_content)
        self.assertIn('OS::Glance::Image', json_content)

        response, json_content = self._request('GET', '/search/plugins',
                                               TENANT1,
                                               role='user')
        self.assertEqual(
            0, len(list(filter(lambda p: p['type'] == 'OS::Nova::Server',
                               json_content['plugins']))))

        response, json_content = self._request('GET', '/search/plugins',
                                               TENANT1,
                                               role='admin')
        self.assertEqual(
            1, len(list(filter(lambda p: p['type'] == 'OS::Nova::Server',
                               json_content['plugins']))))

    def test_domain_token_401(self):
        tenant_id = None
        domain_id = "default"
        response, content = self._request(
            "POST", "/search", tenant_id, {"query": {"match_all": {}}},
            decode_json=False,
            extra_headers={"X-Domain-Id": domain_id})
        self.assertEqual(401, response.status_code)

    def test_search_version(self):
        id_1 = uuidutils.generate_uuid()
        tenant1_doc = {
            "owner": TENANT1,
            "id": id_1,
            "visibility": "public",
            "created_at": "2016-04-06T12:48:18Z",
            "updated_at": "2016-04-06T12:48:18Z"
        }
        self._index(self.initialized_plugins['OS::Glance::Image'],
                    [tenant1_doc])
        query = {"query": {"match_all": {}},
                 "type": "OS::Glance::Image",
                 "version": True}
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="user")
        self.assertEqual(1, json_content['hits']['total'])
        self.assertIn('_version', json_content['hits']['hits'][0])

    def test_aggregations(self):
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        images_plugin = self.initialized_plugins['OS::Glance::Image']
        volumes_plugin = self.initialized_plugins['OS::Cinder::Volume']
        server_doc = {
            u'addresses': {},
            u'id': 'abcdef',
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z'
        }

        image_doc = {
            "owner": TENANT1,
            "id": "1234567890",
            "visibility": "public",
            "name": "for_instance1",
            "created_at": "2016-04-06T12:48:18Z"
        }

        volume_doc = {
            "os-vol-tenant-attr:tenant_id": TENANT1,
            "user_id": USER1,
            "id": "deadbeef",
            "name": "for_instance1",
            "created_at": "2016-04-06T12:48:18Z",
            "updated_at": "2016-04-06T12:48:18Z",
            "volume_type": "lvmdriver-1"
        }

        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(servers_plugin, [test_utils.DictObj(**server_doc)])
        self._index(images_plugin, [image_doc])
        self._index(volumes_plugin, [test_utils.DictObj(**volume_doc)])

        query = {
            "limit": 0,
            "query": {"match_all": {}},
            "aggregations": {
                "names": {"terms": {"field": "name"}},
                "earliest": {"min": {"field": "created_at"}}
            }
        }
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        expected_aggregations = {
            "names": {
                "doc_count_error_upper_bound": 0,
                "sum_other_doc_count": 0,
                "buckets": [
                    {"key": "for_instance1", "doc_count": 2},
                    {"key": "instance1", "doc_count": 1}
                ]
            },
            "earliest": {
                "value": 1459946898000.0,
                "value_as_string": "2016-04-06T12:48:18.000Z"}
        }
        # Expect a total count but no hit documents
        self.assertEqual({"total": 3, "max_score": 0.0, "hits": []},
                         json_content["hits"])
        # Should see "aggregations" at the top level
        self.assertIn("aggregations", json_content)
        self.assertEqual(expected_aggregations, json_content["aggregations"])

    def test_aggregation_rbac(self):
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        images_plugin = self.initialized_plugins['OS::Glance::Image']
        server_doc = {
            u'addresses': {},
            u'id': 'abcdef',
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z'
        }

        image_doc = {
            "owner": TENANT1,
            "id": "1234567890",
            "visibility": "public",
            "name": "for_instance1",
            "created_at": "2016-04-06T12:48:18Z"
        }

        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(servers_plugin, [test_utils.DictObj(**server_doc)])
        self._index(images_plugin, [image_doc])

        # Set type to ignore the image for all queries
        query = {
            "limit": 0,
            "type": "OS::Nova::Server",
            "query": {"match_all": {}},
            "aggregations": {
                "names": {"terms": {"field": "name"}}
            }
        }

        expected_aggregation = {
            "names": {
                "doc_count_error_upper_bound": 0,
                "sum_other_doc_count": 0,
                "buckets": [
                    {"key": "instance1", "doc_count": 1}
                ]
            }
        }

        expected_aggregation_no_results = {
            "names": {
                "doc_count_error_upper_bound": 0,
                "sum_other_doc_count": 0,
                "buckets": []
            }
        }

        # Expected aggregation results
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="member")
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual(expected_aggregation, json_content['aggregations'])

        # Now with a different tenant
        response, json_content = self._search_request(query,
                                                      TENANT2,
                                                      role="member")
        self.assertEqual(0, json_content['hits']['total'])
        self.assertEqual(expected_aggregation_no_results,
                         json_content['aggregations'])

        # Now with all_projects
        query['all_projects'] = True
        response, json_content = self._search_request(query,
                                                      TENANT2,
                                                      role="member")
        self.assertEqual(0, json_content['hits']['total'])
        self.assertEqual(expected_aggregation_no_results,
                         json_content['aggregations'])

        # Now admin all projects
        response, json_content = self._search_request(query,
                                                      TENANT2,
                                                      role="admin")
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual(expected_aggregation, json_content['aggregations'])

    def test_global_aggregation_not_allowed(self):
        query = {
            "limit": 0,
            "query": {"match_all": {}},
            "aggregations": {
                "cheating": {
                    "global": {},
                    "aggs": {
                        "names": {"terms": {"field": "name"}}
                    }
                }
            }
        }

        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin",
                                                      decode_json=False)
        # TODO(sjmc7) Grr! https://bugs.launchpad.net/searchlight/+bug/1610398
        self.assertNotEqual(200, response.status_code)
        # self.assertEqual(403, response.status_code)

    def test_aggregation_policy(self):
        query = {
            "limit": 0,
            "query": {"match_all": {}},
            "aggregations": {
                "names": {"terms": {"field": "name"}}
            }
        }

        # Alter the default policy to allow aggregation only for admins
        self._modify_policy_file({'search:query:aggregations': 'role:admin'})

        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="member",
                                                      decode_json=False)
        self.assertEqual(403, response.status_code)

        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual(200, response.status_code)

        # Now let nobody use aggregations
        self._modify_policy_file({'search:query:aggregations': '!'})

        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="member",
                                                      decode_json=False)
        self.assertEqual(403, response.status_code)

        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin",
                                                      decode_json=False)
        self.assertEqual(403, response.status_code)

    def test_is_admin_project(self):
        """The X-IS-ADMIN-PROJECT header is the current solution to the
        problems caused by the overloaded 'admin' role. It's only set if
        configured in keystone, and defaults to True for back compatibility.
        """
        one_tenant_doc = {
            u'addresses': {},
            u'id': 'abcdef',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            u'status': 'ACTIVE',
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z'
        }
        two_tenant_doc = {
            u'addresses': {},
            u'id': '12341234',
            u'tenant_id': TENANT2,
            u'user_id': USER1,
            u'status': 'ACTIVE',
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z'
        }

        # A request with HTTP_X_IS_ADMIN_PROJECT=false should not allow a
        # TENANT1-scoped request to retrieve both servers if set to True it
        # should (assuming they also have the admin role)
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(servers_plugin, [test_utils.DictObj(**one_tenant_doc),
                                         test_utils.DictObj(**two_tenant_doc)])

        query = {"type": "OS::Nova::Server",
                 "all_projects": True,
                 "query": {"match_all": {}},
                 "sort": "id"}
        # First try admin request, is-admin-project false
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin",
                                                      is_admin_project=False)
        self.assertEqual(['abcdef_USER'],
                         [h['_id'] for h in json_content['hits']['hits']])

        # Now try with is_admin_project True
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin",
                                                      is_admin_project=True)
        self.assertEqual(['12341234_ADMIN', 'abcdef_ADMIN'],
                         [h['_id'] for h in json_content['hits']['hits']])

        # Now try with is_admin_project True but member role
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="member",
                                                      is_admin_project=True)
        self.assertEqual(['abcdef_USER'],
                         [h['_id'] for h in json_content['hits']['hits']])


class TestServerServicePolicies(functional.FunctionalTest):
    def _write_policy_file(self, filename, rules):
        with open(os.path.join(self.conf_dir, filename), 'w') as pol_file:
            jsonutils.dump(rules, pol_file)

    def _additional_server_config(self):
        """Create some service policy files"""
        super(TestServerServicePolicies, self)._additional_server_config()
        self.api_server.service_policy_files = ','.join([
            'image:glance-policy.json',
            'compute:' + os.path.join(self.conf_dir, 'nova-policy.json'),
            'volume:' + os.path.join(self.conf_dir, 'cinder-policy.json')])

        self.api_server.service_policy_path = self.conf_dir

        self._write_policy_file(
            'glance-policy.json',
            {'is_admin': 'role:admin', 'get_images': 'rule:is_admin'})
        self._write_policy_file(
            'nova-policy.json',
            {'os_compute_api:servers:index': '',
             'os_compute_api:os-hypervisors': 'is_admin:True'})
        self._write_policy_file(
            'cinder-policy.json',
            {'admin_or_owner': 'role:admin or project_id:%(project_id)s',
             'volume:get_all': 'rule:admin_or_owner'})

    def test_server_starts(self):
        """Test that with policy changes, the server still starts"""
        self.assertTrue(self.ping_server(self.api_port))

    def test_service_policy_facet(self):
        response, json_content = self._facet_request(TENANT1,
                                                     role="user")
        self.assertEqual(200, response.status_code)
        self.assertIn('OS::Nova::Server', json_content)
        self.assertIn('OS::Cinder::Volume', json_content)
        self.assertNotIn('OS::Glance::Image', json_content)
        # Next one tests is_admin which is a magic context rule
        self.assertNotIn('OS::Nova::Hypervisor', json_content)

        response, json_content = self._facet_request(TENANT1,
                                                     role="admin")
        self.assertEqual(200, response.status_code)
        self.assertIn('OS::Nova::Server', json_content)
        self.assertIn('OS::Glance::Image', json_content)
        self.assertIn('OS::Cinder::Volume', json_content)
        # Magic context rule should pass this time
        self.assertIn('OS::Nova::Hypervisor', json_content)

    def test_service_policy_search(self):
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        images_plugin = self.initialized_plugins['OS::Glance::Image']
        volumes_plugin = self.initialized_plugins['OS::Cinder::Volume']
        server_doc = {
            u'addresses': {},
            u'id': 'abcdef',
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            u'image': {u'id': u'a'},
            u'flavor': {u'id': u'1'},
            u'created_at': u'2016-04-07T15:49:35Z',
            u'updated_at': u'2016-04-07T15:51:35Z'
        }

        image_doc = {
            "owner": TENANT1,
            "id": "1234567890",
            "visibility": "public",
            "name": "image",
            "created_at": "2016-04-06T12:48:18Z"
        }

        volume_doc = {
            "os-vol-tenant-attr:tenant_id": TENANT1,
            "user_id": USER1,
            "id": "deadbeef",
            "created_at": "2016-04-06T12:48:18Z",
            "updated_at": "2016-04-06T12:48:18Z",
            "volume_type": "lvmdriver-1"
        }

        with mock.patch(nova_version_getter, return_value=fake_version_list):
            self._index(servers_plugin, [test_utils.DictObj(**server_doc)])
        self._index(images_plugin, [image_doc])
        self._index(volumes_plugin, [test_utils.DictObj(**volume_doc)])

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="user")
        self.assertEqual(200, response.status_code)
        self.assertEqual(2, json_content['hits']['total'])
        self.assertEqual(
            set([server_doc['id'], volume_doc['id']]),
            set(h['id'] for h in self._get_hit_source(json_content)))

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual(200, response.status_code)
        self.assertEqual(3, json_content['hits']['total'])
        self.assertEqual(
            set([server_doc['id'], image_doc['id'], volume_doc['id']]),
            set(s['id'] for s in self._get_hit_source(json_content)))

    def test_service_policy_forbidden_none_allowed(self):
        query = {"type": "OS::Glance::Image", "query": {"match_all": {}}}
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="user",
                                                      decode_json=False)
        self.assertEqual(403, response.status_code)
