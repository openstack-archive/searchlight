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

import datetime
from unittest import mock

from oslo_config import cfg
import oslo_utils

from searchlight.cmd import manage
from searchlight.elasticsearch.plugins import utils as es_utils
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import fake_plugins
from searchlight.tests import functional
from searchlight.tests import utils as test_utils


now = oslo_utils.timeutils.utcnow()
now_str = now.strftime(es_utils.FORMAT)


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
        index_name = self.role_plugin.alias_name_listener
        doc_type = self.role_plugin.document_type

        self.role_plugin.index_initial_data()
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
        self.assertIn('admin_specific', admin1_doc['_source'])
        self.assertIn('admin_wildcard_this', admin1_doc['_source'])
        self.assertIn('public_field', admin1_doc['_source'])
        self.assertEqual('admin',
                         admin1_doc['_source'][ROLE_USER_FIELD])

        user1_doc = self._get_elasticsearch_doc(
            index_name, doc_type, 'role-fake1_USER'
        )
        self.assertNotIn('admin_specific', user1_doc['_source'])
        self.assertNotIn('admin_wildcard_this', user1_doc['_source'])
        self.assertIn('public_field', user1_doc['_source'])
        self.assertEqual('admin',
                         admin1_doc['_source'][ROLE_USER_FIELD])

    def test_non_separated(self):
        index_name = self.non_role_plugin.alias_name_listener

        self.non_role_plugin.index_initial_data()
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

    def test_index_settings(self):
        """Test the default gc_delete interval plus some other
        dynamic index settings
        """
        with mock.patch.object(cfg.CONF, 'elasticsearch') as mock_settings:
            mock_settings.index_gc_deletes = '100s'
            mock_settings.index_settings = {
                'refresh_interval': '2s',
                'index.number_of_replicas': 1
            }

            index_name = es_utils.create_new_index('test-index-settings')
            try:
                settings = self.elastic_connection.indices.get_settings(
                    index_name)
                index_settings = settings[index_name]['settings']['index']

                self.assertEqual("100s", index_settings['gc_deletes'])
                self.assertEqual("2s", index_settings['refresh_interval'])
                self.assertEqual("1", index_settings['number_of_replicas'])

            finally:
                es_utils.delete_index(index_name)

    @mock.patch('oslo_utils.timeutils.utcnow')
    @mock.patch('searchlight.common.utils.get_search_plugins')
    def test_manage(self, mock_get_plugins, mock_utcnow):
        """Test that manage index sync works from end to end. Uses fake plugins
        because it avoids having to fake service data and is less dependent
        on functional tests for each service plugin.
        """
        mock_utcnow.return_value = datetime.datetime(year=2016, month=1, day=1)
        expected_index_name = 'searchlight-2016_01_01_00_00_00'

        simple_plugin = fake_plugins.FakeSimplePlugin(self.elastic_connection)
        child_plugin = fake_plugins.FakeChildPlugin(self.elastic_connection)
        non_role_plugin = fake_plugins.NonRoleSeparatedPlugin(
            self.elastic_connection)
        child_plugin.register_parent(simple_plugin)

        mock_get_plugins.return_value = {
            plugin.get_document_type(): test_utils.StevedoreMock(plugin)
            for plugin in (simple_plugin, child_plugin, non_role_plugin)
        }
        index_command = manage.IndexCommands()
        # The fake plugins all have hardcoded data for get_objects that will
        # be indexed. Use force=True to avoid the 'are you sure?' prompt
        try:
            index_command.sync(force=True)

            es_results = self._get_all_elasticsearch_docs()
            es_hits = self._get_hit_source(es_results)
        finally:
            es_utils.delete_index(expected_index_name)

        self.assertEqual(expected_index_name,
                         es_results['hits']['hits'][0]['_index'])

        expected = ['simple1', 'child1', 'non-role-fake1', 'non-role-fake2']
        self.assertEqual(len(expected), len(es_hits))
        self.assertEqual(
            set(expected),
            set(hit['_id'] for hit in es_results['hits']['hits']))

    @mock.patch('oslo_utils.timeutils.utcnow')
    @mock.patch('searchlight.common.utils.get_search_plugins')
    def test_manage_type(self, mock_get_plugins, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime(year=2016, month=2, day=2)
        expected_index_name = 'searchlight-2016_02_02_00_00_00'

        simple_plugin = fake_plugins.FakeSimplePlugin(self.elastic_connection)
        non_role_plugin = fake_plugins.NonRoleSeparatedPlugin(
            self.elastic_connection)

        mock_get_plugins.return_value = {
            plugin.get_document_type(): test_utils.StevedoreMock(plugin)
            for plugin in (simple_plugin, non_role_plugin)
        }
        index_command = manage.IndexCommands()

        # Expect this to match simple plugin and child plugin, but not
        # non_role_plugin. Patch the index->index function call since it won't
        # find any data, and we want to check it's called correctly
        with mock.patch.object(index_command,
                               '_es_reindex_worker') as patch_es_reindex:
            try:
                index_command.sync(_type='fake-simple', force=True)

                es_results = self._get_all_elasticsearch_docs()
                es_hits = self._get_hit_source(es_results)
            finally:
                es_utils.delete_index(expected_index_name)

            patch_es_reindex.assert_called_with(
                {non_role_plugin.get_document_type(): non_role_plugin},
                [('searchlight', 'searchlight-search',
                 'searchlight-listener')],
                {'searchlight': expected_index_name}
            )

        expected = ['simple1']
        self.assertEqual(len(expected), len(es_hits))
        self.assertEqual(
            set(expected),
            set(hit['_id'] for hit in es_results['hits']['hits']))

    @mock.patch('oslo_utils.timeutils.utcnow')
    @mock.patch('searchlight.common.utils.get_search_plugins')
    def test_manage_type_glob(self, mock_get_plugins, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime(year=2016, month=3, day=3)
        expected_index_name = 'searchlight-2016_03_03_00_00_00'

        simple_plugin = fake_plugins.FakeSimplePlugin(self.elastic_connection)
        child_plugin = fake_plugins.FakeChildPlugin(self.elastic_connection)
        non_role_plugin = fake_plugins.NonRoleSeparatedPlugin(
            self.elastic_connection)
        child_plugin.register_parent(simple_plugin)

        mock_get_plugins.return_value = {
            plugin.get_document_type(): test_utils.StevedoreMock(plugin)
            for plugin in (simple_plugin, child_plugin, non_role_plugin)
        }
        index_command = manage.IndexCommands()

        # Expect this to match simple plugin and child plugin, but not
        # non_role_plugin. Patch the index->index function call since it won't
        # find any data, and we want to check it's called correctly
        with mock.patch.object(index_command,
                               '_es_reindex_worker') as patch_es_reindex:
            try:
                # Use two wildcard matches
                index_command.sync(_type='fake-sim*,fake-chi*', force=True)

                es_results = self._get_all_elasticsearch_docs()
                es_hits = self._get_hit_source(es_results)
            finally:
                es_utils.delete_index(expected_index_name)

            patch_es_reindex.assert_called_with(
                {non_role_plugin.get_document_type(): non_role_plugin},
                [('searchlight', 'searchlight-search',
                 'searchlight-listener')],
                {'searchlight': expected_index_name}
            )

        expected = ['simple1', 'child1']
        self.assertEqual(len(expected), len(es_hits))
        self.assertEqual(
            set(expected),
            set(hit['_id'] for hit in es_results['hits']['hits']))

    @mock.patch.object(cfg.CONF, 'service_credentials')
    @mock.patch.object(cfg.CONF, 'resource_plugin')
    def test_without_region(self, resource_plugin_conf, service_cred_conf):
        # Test that region isn't indexed unless explicitly enabled
        resource_plugin_conf.include_region_name = False
        service_cred_conf.os_region_name = 'test-region'
        index_name = self.role_plugin.alias_name_listener
        simple_plugin = fake_plugins.FakeSimplePlugin(self.elastic_connection)

        simple_plugin.index_initial_data()
        self._flush_elasticsearch(index_name)

        es_results = self._get_all_elasticsearch_docs()
        self.assertNotIn('region_name',
                         es_results['hits']['hits'][0]['_source'])

    @mock.patch.object(cfg.CONF, 'service_credentials')
    @mock.patch.object(cfg.CONF, 'resource_plugin')
    def test_with_region(self, resource_plugin_conf, service_cred_conf):
        # Now test with a region
        resource_plugin_conf.include_region_name = True
        service_cred_conf.os_region_name = 'test-region'

        index_name = self.role_plugin.alias_name_listener

        simple_plugin = fake_plugins.FakeSimplePlugin(self.elastic_connection)
        non_role = fake_plugins.NonRoleSeparatedPlugin(self.elastic_connection)

        # Override region name for non-role
        non_role.options.override_region_name = ['region1', 'region2']

        non_role.index_initial_data()
        simple_plugin.index_initial_data()
        self._flush_elasticsearch(index_name)

        es_results = self._get_all_elasticsearch_docs()

        simple_res = list(filter(
            lambda r: r['_type'] == simple_plugin.get_document_type(),
            es_results['hits']['hits']))
        non_role_res = list(filter(
            lambda r: r['_type'] == non_role.get_document_type(),
            es_results['hits']['hits']))

        self.assertEqual(
            ['test-region'],
            simple_res[0]['_source']['region_name'])

        self.assertEqual(['region1', 'region2'],
                         non_role_res[0]['_source']['region_name'])
