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


import elasticsearch
import httplib2
import json
import mock
import six

from oslo_serialization import jsonutils


from searchlight.elasticsearch.plugins.glance import images
from searchlight.elasticsearch.plugins.glance import metadefs
from searchlight.tests import functional
from searchlight.tests.functional import generate_load_data
from searchlight.tests.functional import mock_glance_pyclient
from searchlight.tests.functional import util as futils
from searchlight.tests.utils import depends_on_exe
from searchlight.tests.utils import skip_if_disabled

MATCH_ALL = {"query": {"match_all": {}}, "sort": [{"name": {"order": "asc"}}]}


class TestSearchLoad(functional.FunctionalTest):

    @depends_on_exe("elasticsearch")
    @skip_if_disabled
    def setUp(self):
        super(TestSearchLoad, self).setUp()
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
            plugin.engine = self.elastic_connection
            plugin.index_name = plugin.get_index_name()
            plugin.document_type = plugin.get_document_type()
            plugin.document_id_field = plugin.get_document_id_field()

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

        openstack_client_mod = "searchlight.elasticsearch.plugins." \
                               "openstack_clients.get_glanceclient"
        osclient_patcher = mock.patch(
            openstack_client_mod, mock_glance_pyclient.get_fake_glance_client
        )
        osclient_patcher.start()
        self.addCleanup(osclient_patcher.stop)

        self.images_plugin = images.ImageIndex()
        self.metadefs_plugin = metadefs.MetadefIndex()

        self.images_count, self.images_owner = \
            self._get_glance_image_owner_and_count()
        self.metadefs_count, self.metadefs_owner = \
            self._get_glance_metadefs_owner_and_count()
        self.all_doc_count = self.images_count + self.metadefs_count

    def tearDown(self):
        super(TestSearchLoad, self).tearDown()

        # There"s no delete_index on the plugin class
        self.elastic_connection.indices.delete(
            index=self.images_plugin.get_index_name())
        # Ignore a 404 from metadefs because it (currently) shares and index
        self.elastic_connection.indices.delete(
            index=self.metadefs_plugin.get_index_name(),
            ignore=404)

    def _flush_elasticsearch(self, index_name=None):
        self.elastic_connection.indices.flush(index_name)

    def _get_glance_image_owner_and_count(self):
        with open(generate_load_data.IMAGES_FILE, "r") as file:
            images_data = json.load(file)
        if len(images_data) > 0:
            return len(images_data), images_data[0]['owner']

    def _get_glance_metadefs_owner_and_count(self):
        with open(generate_load_data.METADEFS_FILE, "r") as file:
            metadefs_data = json.load(file)
        if len(metadefs_data) > 0:
            return len(metadefs_data), metadefs_data[0]['owner']

    def _get_hit_source(self, es_response):
        """Parse the _source from the elasticsearch hits"""
        if six.PY2:
            if isinstance(es_response, basestring):
                es_response = jsonutils.loads(es_response)
        else:
            if isinstance(es_response, str):
                es_response = jsonutils.loads(es_response)
        return [h["_source"] for h in es_response["hits"]["hits"]]

    def test_searchlight_glance_images_data(self):
        """Test that all the indexed images data is served from api server"""

        self.images_plugin.initial_indexing()
        self._flush_elasticsearch(self.images_plugin.get_index_name())
        glance_images_query = MATCH_ALL.copy()
        glance_images_query['index'] = self.images_plugin.get_index_name()
        glance_images_query['type'] = self.images_plugin.get_document_type()
        response, json_content = futils.search_request(
            self.base_url,
            glance_images_query,
            self.images_owner)
        self.assertEqual(self.images_count,
                         futils.get_json(json_content)['hits']['total'])

    def test_searchlight_glance_metadefs_data(self):
        """Test that all the indexed metadefs data is served from api server"""
        self.metadefs_plugin.initial_indexing()
        self._flush_elasticsearch(self.metadefs_plugin.get_index_name())
        metadefs_query = MATCH_ALL.copy()
        metadefs_query['index'] = self.metadefs_plugin.get_index_name()
        metadefs_query['type'] = self.metadefs_plugin.get_document_type()
        response, json_content = futils.search_request(self.base_url,
                                                       metadefs_query,
                                                       self.metadefs_owner)
        self.assertEqual(self.metadefs_count,
                         futils.get_json(json_content)['hits']['total'])

    def test_es_all_data(self):
        """Test that all the data is indexed in elasticsearch server"""

        for plugin in self.images_plugin, self.metadefs_plugin:
            plugin.initial_indexing()
        self._flush_elasticsearch(self.images_plugin.get_index_name())
        # Test the raw elasticsearch response
        es_url = "http://localhost:%s/_search" % (
            self.api_server.elasticsearch_port)

        response, content = httplib2.Http().request(es_url)
        json_content = jsonutils.loads(content)
        self.assertEqual(self.all_doc_count,
                         futils.get_json(json_content)['hits']['total'])
