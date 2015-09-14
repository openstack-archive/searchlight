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


import copy
import elasticsearch
import httplib2
import mock
from oslo_serialization import jsonutils
import six
import uuid

from searchlight.elasticsearch.plugins.glance import images
from searchlight.elasticsearch.plugins.glance import metadefs
from searchlight.tests import functional
from searchlight.tests.utils import depends_on_exe
from searchlight.tests.utils import skip_if_disabled

TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())

MATCH_ALL = {"query": {"match_all": {}}, "sort": [{"name": {"order": "asc"}}]}
EMPTY_RESPONSE = {"hits": {"hits": [], "total": 0, "max_score": 0.0},
                  "_shards": {"successful": 0, "failed": 0, "total": 0},
                  "took": 1,
                  "timed_out": False}


class TestSearchApi(functional.FunctionalTest):

    @depends_on_exe("elasticsearch")
    @skip_if_disabled
    def setUp(self):
        super(TestSearchApi, self).setUp()
        self.api_server.deployment_flavor = "trusted-auth"
        # Use the role-based policy file all over; we need it for the property
        # protection tests
        self.api_server.property_protection_file = self.property_file_roles

        self.base_url = "http://127.0.0.1:%d/v1" % self.api_port
        self.start_with_retry(self.api_server,
                              "api_port",
                              max_retries=3,
                              **self.__dict__.copy())

        self.elastic_connection = elasticsearch.Elasticsearch(
            "http://localhost:%s" % self.api_server.elasticsearch_port)

        def dummy_plugin_init(plugin):
            plugin.options = mock.Mock()
            plugin.options.index_name = "searchlight"
            plugin.options.enabled = True

            plugin.engine = self.elastic_connection
            plugin.index_name = plugin.get_index_name()
            plugin.document_type = plugin.get_document_type()

        plugins = {
            "glance": ["images", "metadefs"]
        }
        for plugin_name, plugin_types in six.iteritems(plugins):
            for plugin_type in plugin_types:
                mod = "searchlight.elasticsearch.plugins.%s.%s.base.IndexBase" \
                      % (plugin_name, plugin_type)
                plugin_patcher = \
                    mock.patch("%s.__init__" % mod, dummy_plugin_init)
                plugin_patcher.start()
                self.addCleanup(plugin_patcher.stop)

        self.images_plugin = images.ImageIndex()
        self.metadefs_plugin = metadefs.MetadefIndex()

        for plugin in self.images_plugin, self.metadefs_plugin:
            plugin.setup_index()
            plugin.setup_mapping()

    def tearDown(self):
        super(TestSearchApi, self).tearDown()

        # There"s no delete_index on the plugin class
        self.elastic_connection.indices.delete(
            index=self.images_plugin.get_index_name())
        # Ignore a 404 from metadefs because it (currently) shares and index
        self.elastic_connection.indices.delete(
            index=self.metadefs_plugin.get_index_name(),
            ignore=404)

    def _flush_elasticsearch(self, index_name=None):
        self.elastic_connection.indices.flush(index_name)

    def _index(self, index_name, doc_type, docs, as_admin=True,
               tenant=TENANT1, refresh_index=True):
        if not isinstance(docs, list):
            docs = [docs]

        index_doc = {"actions": [
            {
                "data": copy.deepcopy(doc),
                "action": "index",
                "index": index_name,
                "id": doc["id"],
                "type": doc_type
            } for doc in docs]
        }

        custom_headers = {
            "X-Tenant-Id": tenant,
            "X-Roles": "admin" if as_admin else "member"
        }
        headers = self._headers(custom_headers)
        http = httplib2.Http()
        response, content = http.request(
            self.base_url + "/index",
            "POST",
            headers=headers,
            body=jsonutils.dumps(index_doc))

        if refresh_index:
            # Force elasticsearch to update its search index
            self._flush_elasticsearch(index_name)

        return response, content

    def _headers(self, custom_headers={}):
        base_headers = {
            "X-Identity-Status": "Confirmed",
            "X-Auth-Token": "932c5c84-02ac-4fe5-a9ba-620af0e2bb96",
            "X-User-Id": "f9a41d13-0c13-47e9-bee2-ce4e8bfe958e",
            "X-Tenant-Id": TENANT1,
            "X-Roles": "member",
            "Content-Type": "application/json"
        }
        base_headers.update(custom_headers)
        return base_headers

    def _search_request(self, body, tenant, role="member", decode_json=True):
        """Conduct a search against all elasticsearch indices unless specified
        in `body`. Returns the response and json-decoded content.
        """
        custom_headers = {
            "X-Tenant-Id": tenant,
            "X-Roles": role,
        }
        headers = self._headers(custom_headers)

        http = httplib2.Http()
        response, content = http.request(
            self.base_url + "/search",
            "POST",
            headers=headers,
            body=jsonutils.dumps(body)
        )
        if decode_json:
            content = jsonutils.loads(content)
        return response, content

    def _get_hit_source(self, es_response):
        """Parse the _source from the elasticsearch hits"""
        if six.PY2:
            if isinstance(es_response, basestring):
                es_response = jsonutils.loads(es_response)
        else:
            if isinstance(es_response, str):
                es_response = jsonutils.loads(es_response)
        return [h["_source"] for h in es_response["hits"]["hits"]]

    def test_server_up(self):
        self.assertTrue(self.ping_server(self.api_port))

    def test_index(self):
        """Index a document and check elasticsearch for it."""
        doc_id = str(uuid.uuid4())
        doc = {
            "owner": TENANT1,
            "is_public": True,
            "id": doc_id,
            "name": "owned by tenant 1",
            "owner": TENANT1,
            "members": [TENANT1]
        }

        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    doc)

        # Test the raw elasticsearch response
        es_url = "http://localhost:%s/%s/%s/%s" % (
            self.api_server.elasticsearch_port,
            self.images_plugin.get_index_name(),
            self.images_plugin.get_document_type(),
            doc_id)

        response, content = httplib2.Http().request(es_url)
        json_content = jsonutils.loads(content)
        self.assertEqual(doc, json_content["_source"])

    def test_empty_results(self):
        """Test an empty dataset gets empty results."""
        response, json_content = self._search_request(MATCH_ALL, TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_image_property_protection(self):
        doc_with_properties = {
            "owner": TENANT1,
            "id": str(uuid.uuid4()),
            "name": "doc with properties",
            "x_none_permitted": "nobody can do anything",
            "x_foo_matcher": "admin only",
            "x_owner_anything": "member or admin",
            "x_none_read": "nobody can read",
            "any_old_property": "restricted to admins",
            "x_foo_anybody": "anybody may read",
            "spl_read_only_prop": "spl_role only"
        }
        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    [doc_with_properties])

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1)
        self.assertEqual(200, response.status)
        expect_removed = ["x_none_permitted", "x_foo_matcher", "x_none_read",
                          "any_old_property", "spl_read_only_prop"]
        expected_result = dict((k, v)
                               for k, v in six.iteritems(doc_with_properties)
                               if k not in expect_removed)

        # Test with the 'spl_role' role
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="spl_role")
        self.assertEqual(200, response.status)
        expect_removed = ["x_none_permitted", "x_foo_matcher", "x_none_read",
                          "any_old_property"]
        expected_result = dict((k, v)
                               for k, v in six.iteritems(doc_with_properties)
                               if k not in expect_removed)

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual(200, response.status)
        expect_removed = ["x_none_permitted", "x_none_read"]
        expected_result = dict((k, v)
                               for k, v in six.iteritems(doc_with_properties)
                               if k not in expect_removed)

        self.assertEqual([expected_result], self._get_hit_source(json_content))

    def test_rbac_admin(self):
        """Test that an admin has access to everything"""
        image_doc = {
            "owner": TENANT1,
            "id": str(uuid.uuid4()),
            "name": "abc",
            "visibility": "private",
            "members": [TENANT1]
        }
        metadef_doc = {
            "owner": TENANT2,
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "def",
            "namespace": "some.value1",
            "members": [TENANT1],
            "properties": [
                {"property": "prop1",
                 "title": "hello"},
                {"property": "prop2",
                 "title": "bye"}
            ]
        }
        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    [image_doc, metadef_doc])

        # An ordinary user in TENANT3 shouldn"t have any access
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT3)
        self.assertEqual([], self._get_hit_source(json_content))

        # An admin without specifying all_projects should get the same
        # result as an ordinary user
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT3,
                                                      role='admin')
        self.assertEqual([], self._get_hit_source(json_content))

        # An admin should have access to all (at least in KS v2)
        admin_match_all = {
            'all_projects': True
        }
        admin_match_all.update(MATCH_ALL)
        response, json_content = self._search_request(admin_match_all,
                                                      TENANT3,
                                                      role='admin')
        self.assertEqual([image_doc, metadef_doc],
                         self._get_hit_source(json_content))

    def test_image_rbac_owner(self):
        """Test glance.image RBAC based on the "owner" field"""
        id_1 = str(uuid.uuid4())
        tenant1_doc = {
            "owner": TENANT1,
            "id": id_1,
            "visibility": "private",
            "name": "owned by tenant 1",
            "members": []
        }
        tenant2_doc = {
            "owner": TENANT2,
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "owned by tenant 2",
            "members": []
        }
        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    [tenant1_doc, tenant2_doc])

        # Query for everything as one tenant then the other
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([tenant1_doc], self._get_hit_source(json_content))

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT2)
        self.assertEqual(200, response.status)
        self.assertEqual([tenant2_doc], self._get_hit_source(json_content))

        # Query the hidden doc explicitly
        query = {
            "query": {
                "match": {"id": id_1}
            }
        }
        response, json_content = self._search_request(query,
                                                      TENANT2)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_image_rbac_member(self):
        """Test glance.image RBAC based on the "member" field"""
        accessible_doc = {
            "owner": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "accessible doc",
            "members": [TENANT1, TENANT2]
        }
        inaccessible_doc = {
            "owner": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "inaccessible_doc doc",
            "members": [str(uuid.uuid4())]
        }
        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    [accessible_doc, inaccessible_doc])

        # Someone in TENANT1 or TENANT2 should have access to "accessible_doc"
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([accessible_doc], self._get_hit_source(json_content))

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT2)
        self.assertEqual(200, response.status)
        self.assertEqual([accessible_doc], self._get_hit_source(json_content))

        response, json_content = self._search_request(MATCH_ALL,
                                                      str(uuid.uuid4()))
        self.assertEqual(200, response.status)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_image_rbac_visibility(self):
        """Test that "visibility: public" makes images visible"""
        visible_doc = {
            "owner": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "visibility": "public",
            "name": "visible doc",
            "members": [str(uuid.uuid4())]
        }
        invisible_doc = {
            "owner": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "visible doc",
            "members": [str(uuid.uuid4())]
        }
        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    [visible_doc, invisible_doc])

        # visible doc should be visible to any user
        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT2)
        self.assertEqual(200, response.status)
        self.assertEqual([visible_doc], self._get_hit_source(json_content))

    def test_metadef_rbac_visibility(self):
        visible_doc = {
            "owner": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "visibility": "public",
            "name": "visible doc",
        }
        invisible_doc = {
            "owner": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "visible doc"
        }
        self._index(self.metadefs_plugin.get_index_name(),
                    self.metadefs_plugin.get_document_type(),
                    [visible_doc, invisible_doc])

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT2)
        self.assertEqual(200, response.status)
        self.assertEqual([visible_doc], self._get_hit_source(json_content))

    def test_metadef_rbac_owner(self):
        visible_doc = {
            "owner": TENANT1,
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "visible doc",
        }
        invisible_doc = {
            "owner": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "visibility": "private",
            "name": "visible doc"
        }
        self._index(self.metadefs_plugin.get_index_name(),
                    self.metadefs_plugin.get_document_type(),
                    [visible_doc, invisible_doc])

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([visible_doc], self._get_hit_source(json_content))

        response, json_content = self._search_request(MATCH_ALL,
                                                      TENANT2)
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
        self._index(self.metadefs_plugin.get_index_name(),
                    self.metadefs_plugin.get_document_type(),
                    [doc1, doc2])

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
