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
import six
import time
import uuid

from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import functional

TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())

USER1 = str(uuid.uuid4())

MATCH_ALL = {"query": {"match_all": {}}, "sort": [{"name": {"order": "asc"}}]}
EMPTY_RESPONSE = {"hits": {"hits": [], "total": 0, "max_score": 0.0},
                  "_shards": {"successful": 0, "failed": 0, "total": 0},
                  "took": 1,
                  "timed_out": False}


class TestSearchApi(functional.FunctionalTest):
    """Test case for API functionality that's not plugin-specific, although
    it can use plugins for the sake of making requests
    """
    def test_server_up(self):
        self.assertTrue(self.ping_server(self.api_port))

    def test_elasticsearch(self):
        """Index a document and check elasticsearch for it to check
        things are working.
        """
        doc_id = str(uuid.uuid4())
        doc = {
            "owner": TENANT1,
            "is_public": True,
            "id": doc_id,
            "name": "owned by tenant 1",
            "owner": TENANT1,
            "members": [TENANT1]
        }

        self._index(self.images_plugin.alias_name_search,
                    self.images_plugin.get_document_type(),
                    doc,
                    TENANT1)

        # Test the raw elasticsearch response
        es_doc = self._get_elasticsearch_doc(
            self.images_plugin.alias_name_search,
            self.images_plugin.get_document_type(),
            doc_id)
        self.assertEqual(['admin', 'user'],
                         es_doc['_source'].pop(ROLE_USER_FIELD))
        self.assertEqual(doc, es_doc['_source'])

    def test_empty_results(self):
        """Test an empty dataset gets empty results."""
        response, json_content = self._search_request(MATCH_ALL, TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_nested_objects(self):
        """Test queries against documents with nested complex objects."""
        doc1 = {
            "owner": TENANT1,
            "is_public": True,
            "id": str(uuid.uuid4()),
            "name": "owned by tenant 1",
            "namespace": "some.value1",
            "members": [TENANT1],
            "properties": [
                {"property": "prop1",
                 "title": "hello"},
                {"property": "prop2",
                 "title": "bye"}
            ]
        }
        doc2 = {
            "owner": TENANT1,
            "is_public": True,
            "id": str(uuid.uuid4()),
            "namespace": "some.value2",
            "name": "owned by tenant 1",
            "members": [TENANT1],
            "properties": [
                {"property": "prop1",
                 "title": "something else"},
                {"property": "prop2",
                 "title": "hello"}
            ]
        }

        self._index(self.metadefs_plugin.alias_name_search,
                    self.metadefs_plugin.get_document_type(),
                    [doc1, doc2],
                    TENANT1)

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
        querystring = "properties.property:prop1"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1, doc2], self._get_hit_source(json_content))

        # Expect this to match only doc1
        querystring = "properties.property:prop1 AND properties.title:hello"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1], self._get_hit_source(json_content))

        # Expect this not to match any documents, because it
        # doesn't properly match any nested objects
        querystring = "properties.property:prop1 AND properties.title:bye"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([], self._get_hit_source(json_content))

        # Expect a match with
        querystring = "properties.property:prop3 OR properties.title:bye"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1], self._get_hit_source(json_content))

    def test_query_none(self):
        """Test search when query is not specified"""
        id_1 = str(uuid.uuid4())
        tenant1_doc = {
            "owner": TENANT1,
            "id": id_1,
            "visibility": "private",
            "name": "owned by tenant 1",
            "members": []
        }

        self._index(self.images_plugin.alias_name_search,
                    self.images_plugin.get_document_type(),
                    [tenant1_doc],
                    TENANT1)

        response, json_content = self._search_request({"all_projects": True},
                                                      TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([tenant1_doc], self._get_hit_source(json_content))

    def test_facets(self):
        """Check facets for a non-nested field (status)"""
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        server1 = {
            u'flavor': {u'id': u'1'},
            u'id': u'6c41b4d1-f0fa-42d6-9d8d-e3b99695aa69',
            u'image': {u'id': u'a'},
            u'name': u'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }
        server2 = {
            u'flavor': {u'id': u'1'},
            u'id': u'08ca6c43-eea8-48d0-bbb2-30c50109d5d8',
            u'image': {u'id': u'a'},
            u'name': u'instance2',
            u'status': u'RESUMING',
            u'tenant_id': TENANT1,
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }
        server3 = {
            u'flavor': {u'id': u'1'},
            u'id': u'08ca6c43-f0fa-48d0-48d0-53453522cda4',
            u'image': {u'id': u'a'},
            u'name': u'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }
        self._index(servers_plugin.alias_name_search,
                    servers_plugin.get_document_type(),
                    [server1, server2, server3],
                    TENANT1)

        response, json_content = self._facet_request(
            TENANT1,
            doc_type="OS::Nova::Server")

        expected = {
            u'name': u'status',
            u'options': [
                {u'doc_count': 2, u'key': u'ACTIVE'},
                {u'doc_count': 1, u'key': u'RESUMING'},
            ],
            u'type': u'string'
        }

        status_facet = list(six.moves.filter(
            lambda f: f['name'] == 'status',
            json_content['OS::Nova::Server']
        ))[0]
        self.assertEqual(
            expected,
            status_facet,
        )

    def test_nested_facets(self):
        """Check facets for a nested field (networks.OS-EXT-IPS:type). We
        expect a single count per server matched, not per object in the
        'networks' field
        """
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        server1 = {
            u'networks': [{
                u'ipv4_addr': u'127.0.0.1',
                u'OS-EXT-IPS:type': u'fixed',
                u'name': u'net4',
            }, {
                u'ipv4_addr': u'127.0.0.1',
                u'OS-EXT-IPS:type': u'fixed',
                u'name': u'net4',
            }],
            u'flavor': {u'id': u'1'},
            u'id': u'6c41b4d1-f0fa-42d6-9d8d-e3b99695aa69',
            u'image': {u'id': u'a'},
            u'name': u'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }

        server2 = {
            u'networks': [{
                u'ipv4_addr': u'127.0.0.1',
                u'OS-EXT-IPS:type': u'fixed',
                u'name': u'net4',
            }, {
                u'ipv4_addr': u'127.0.0.1',
                u'OS-EXT-IPS:type': u'floating',
                u'name': u'net4',
            }],
            u'flavor': {u'id': u'1'},
            u'id': u'08ca6c43-eea8-48d0-bbb2-30c50109d5d8',
            u'image': {u'id': u'a'},
            u'name': u'instance2',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': u'27f4d76b-be62-4e4e-aa33bb11cc55'
        }

        self._index(servers_plugin.alias_name_search,
                    servers_plugin.get_document_type(),
                    [server1, server2],
                    TENANT1)

        response, json_content = self._facet_request(
            TENANT1,
            doc_type="OS::Nova::Server")

        self.assertEqual(['OS::Nova::Server'],
                         list(six.iterkeys(json_content)))

        # server1 has two fixed addresses (which should be rolled up into one
        # match). server2 has fixed and floating addresses.
        expected = {
            u'name': u'networks.OS-EXT-IPS:type',
            u'options': [
                {u'doc_count': 2, u'key': u'fixed'},
                {u'doc_count': 1, u'key': u'floating'},
            ],
            u'type': u'string'
        }
        fixed_network_facet = list(six.moves.filter(
            lambda f: f['name'] == 'networks.OS-EXT-IPS:type',
            json_content['OS::Nova::Server']
        ))[0]
        self.assertEqual(
            expected,
            fixed_network_facet,
        )

    def test_server_role_field_rbac(self):
        """Check that admins and users get different versions of documents"""
        doc_id = u'abc'
        doc = {
            u'OS-DCF:diskConfig': u'MANUAL',
            u'OS-EXT-AZ:availability_zone': u'nova',
            u'OS-EXT-SRV-ATTR:host': u'devstack',
            u'OS-EXT-SRV-ATTR:hypervisor_hostname': u'devstack',
            u'OS-EXT-SRV-ATTR:instance_name': u'instance-00000001',
            u'id': doc_id,
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1
        }

        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        servers_plugin.index_helper.save_document(doc)
        self._flush_elasticsearch(servers_plugin.alias_name_listener)

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual(200, response.status)
        self.assertEqual(1, len(json_content['hits']['hits']))
        hit = json_content['hits']['hits'][0]
        self.assertEqual(doc_id + "_ADMIN", hit['_id'])
        self.assertEqual(doc, hit['_source'])

        # Now as a non admin
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="member")
        self.assertEqual(200, response.status)
        self.assertEqual(1, len(json_content['hits']['hits']))
        hit = json_content['hits']['hits'][0]
        self.assertEqual(doc_id + "_USER", hit['_id'])
        for k, v in six.iteritems(hit):
            self.assertFalse(k.startswith('OS-EXT-SRV-ATTR:'),
                             'No protected attributes should be present')

        for field in (u'status', u'OS-DCF:diskConfig'):
            self.assertTrue(field in hit['_source'])

    def test_role_fishing(self):
        """Run some searches to ward against 'fishing' type attacks such that
        'admin only' fields can't be searched by ordinary users
        """
        admin_field, admin_value = (u'OS-EXT-SRV-ATTR:host', u'devstack')

        doc_id = u'abc'
        doc = {
            u'id': doc_id,
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1,
            admin_field: admin_value
        }

        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        servers_plugin.index_helper.save_document(doc)
        self._flush_elasticsearch(servers_plugin.alias_name_listener)

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
            self.assertEqual(200, response.status)
            self.assertEqual(1, json_content['hits']['total'],
                             "No results for: %s" % query)
            self.assertEqual(doc_id + '_ADMIN',
                             json_content['hits']['hits'][0]['_id'])

            # The same search should not work for users
            response, json_content = self._search_request(full_query,
                                                          TENANT1,
                                                          role="user")
            self.assertEqual(200, response.status)
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
            self.assertEqual(200, response.status)
            self.assertEqual(1, json_content['hits']['total'],
                             "No results for: %s %s" % (query, json_content))
            self.assertEqual(doc_id + '_USER',
                             json_content['hits']['hits'][0]['_id'])

    def test_resource_policy(self):
        servers_plugin = self.initialized_plugins['OS::Nova::Server']
        server_doc = {
            u'id': 'abcdef',
            u'name': 'instance1',
            u'status': u'ACTIVE',
            u'tenant_id': TENANT1,
            u'user_id': USER1
        }
        servers_plugin.index_helper.save_document(server_doc)

        image_doc = {
            "owner": TENANT1,
            "id": "1234567890",
            "visibility": "public",
            "name": "image",
        }
        self.images_plugin.index_helper.save_document(image_doc)
        self._flush_elasticsearch(servers_plugin.alias_name_listener)
        self._flush_elasticsearch(self.images_plugin.alias_name_listener)

        # Modify the policy file to disallow some things
        with open(self.policy_file, 'r') as policy_file:
            existing_policy = json.load(policy_file)

        existing_policy["resource:OS::Nova::Server:allow"] = "role:admin"
        existing_policy["resource:OS::Nova::Server:facets"] = "!"

        existing_policy["resource:OS::Glance::Image:facets"] = "!"

        existing_policy["resource:OS::Glance::Metadef:facets"] = "role:admin"

        with open(self.policy_file, 'w') as policy_file:
            json.dump(existing_policy, policy_file)

        # Policy file reloads; sleep until then
        time.sleep(2)

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
        self.assertNotIn('OS::Glance::Image', json_content)
        self.assertNotIn('OS::Glance::Metadef', json_content)

        response, json_content = self._facet_request(TENANT1, role="admin")
        # We DO expect some facets for metadefs for admins
        self.assertIn('OS::Glance::Metadef', json_content)
        # .. but not Server or Image
        self.assertNotIn('OS::Nova::Server', json_content)
        self.assertNotIn('OS::Glance::Image', json_content)

        response, json_content = self._request('GET', '/search/plugins',
                                               TENANT1,
                                               role='user')
        self.assertEqual(
            0, len(list(filter(lambda p: p['name'] == 'OS::Nova::Server',
                               json_content['plugins']))))

        response, json_content = self._request('GET', '/search/plugins',
                                               TENANT1,
                                               role='admin')
        self.assertEqual(
            1, len(list(filter(lambda p: p['name'] == 'OS::Nova::Server',
                               json_content['plugins']))))
