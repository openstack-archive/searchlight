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

from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import fake_plugins
from searchlight.tests import functional


class TestSearchLoad(functional.FunctionalTest):
    def setUp(self):
        super(TestSearchLoad, self).setUp()
        role_plugin = fake_plugins.RoleSeparatedPlugin(
            es_engine=self.elastic_connection)
        self.role_plugin = role_plugin

        non_role_plugin = fake_plugins.NonRoleSeparatedPlugin(
            es_engine=self.elastic_connection)

        self.non_role_plugin = non_role_plugin

        self.initialized_plugins['non-role-separated'] = non_role_plugin
        self.initialized_plugins['role-separated'] = role_plugin

    def test_role_separation(self):
        index_name = self.role_plugin.index_name
        doc_type = self.role_plugin.document_type

        self.role_plugin.initial_indexing()
        self._flush_elasticsearch(index_name)

        # Should be 4 documents from the original two source ones
        self.assertEqual(2, self.role_plugin.number_documents)
        es_results = self._get_all_elasticsearch_docs()

        self.assertEqual(
            set(['role-fake1_ADMIN', 'role-fake2_ADMIN',
                 'role-fake1_USER', 'role-fake2_USER']),
            set(hit['_id'] for hit in es_results['hits']['hits']))

        admin1_doc = self._get_elasticsearch_doc(
            index_name, doc_type, 'role-fake1_ADMIN'
        )
        self.assertTrue('admin_specific' in admin1_doc['_source'])
        self.assertTrue('admin_wildcard_this' in admin1_doc['_source'])
        self.assertTrue('public_field' in admin1_doc['_source'])
        self.assertEqual('admin',
                         admin1_doc['_source'][ROLE_USER_FIELD])

        user1_doc = self._get_elasticsearch_doc(
            index_name, doc_type, 'role-fake1_USER'
        )
        self.assertFalse('admin_specific' in user1_doc['_source'])
        self.assertFalse('admin_wildcard_this' in user1_doc['_source'])
        self.assertTrue('public_field' in user1_doc['_source'])
        self.assertEqual('admin',
                         admin1_doc['_source'][ROLE_USER_FIELD])

    def test_non_separated(self):
        index_name = self.non_role_plugin.index_name

        self.non_role_plugin.initial_indexing()
        self._flush_elasticsearch(index_name)

        self.assertEqual(2, self.non_role_plugin.number_documents)
        es_results = self._get_all_elasticsearch_docs()
        es_hits = self._get_hit_source(es_results)

        self.assertEqual(2, len(es_hits))
        self.assertEqual(
            set(['non-role-fake1', 'non-role-fake2']),
            set(hit['_id'] for hit in es_results['hits']['hits']))

        self.assertEqual(
            ['admin', 'user'], sorted(es_hits[0][ROLE_USER_FIELD]))

    def test_gc_delete_setting(self):
        index_name = self.images_plugin.index_name
        settings = self.elastic_connection.indices.get_settings(index_name)
        self.assertEqual(
            "300s", settings[index_name]['settings']['index']['gc_deletes'])
