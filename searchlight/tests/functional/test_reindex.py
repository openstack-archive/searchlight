# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
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

from searchlight.elasticsearch.plugins import utils as es_utils
from searchlight.tests import fake_plugins
from searchlight.tests import functional


class TestReindexing(functional.FunctionalTest):
    def __init__(self, *args, **kwargs):
        super(TestReindexing, self).__init__(*args, **kwargs)

    def setUp(self):
        super(TestReindexing, self).setUp()
        role_plugin = fake_plugins.RoleSeparatedPlugin(
            es_engine=self.elastic_connection)
        self.role_plugin = role_plugin

        non_role_plugin = fake_plugins.NonRoleSeparatedPlugin(
            es_engine=self.elastic_connection)
        self.non_role_plugin = non_role_plugin

        self.initialized_plugins['re-non-role-separated'] = non_role_plugin
        self.initialized_plugins['re-role-separated'] = role_plugin

    def create_es_documents(self, index):
        """Create a set of documents in ElasticSearch.
           Call all plugins used by the tests to dump their documents
           into ElasticSearch. This is the baseline for each test.
           There are 4 documents from the role plugin and 2 documents
           form the non-role plugin.
        """
        self.role_plugin.index_initial_data()
        self.non_role_plugin.index_initial_data()
        self.num_docs = 6
        self._flush_elasticsearch(index)

    def verify_initial_state(self):
        """Verify the initial state of ElasticSearch. This state is identical
           for all of the tests.
        """
        es_docs = self._get_all_elasticsearch_docs()
        self.assertEqual(self.num_docs, es_docs['hits']['total'])

    def verify_reindex_state(self, new_index):
        """Verify the state of ElasticSearch after the first reindex.
           This state is identical for all of the tests. At this point
           there should be a full set of documents both indices. The
           first check verifies both sets. The second check verifies
           the new index only.
        """
        es_docs = self._get_all_elasticsearch_docs()
        self.assertEqual((2 * self.num_docs), es_docs['hits']['total'])
        es_docs = self._get_all_elasticsearch_docs([new_index])
        self.assertEqual(self.num_docs, es_docs['hits']['total'])

    def verify_new_alias_state(self, new_index, alias_search, alias_listener):
        """Verify the state of ElasticSearch after the aliases are updated.
           This state is identical for all of the tests. At this point there
           should be only one set of documents. The first check verifies the
           number of documents. The next checks verify the aliases are correct.
        """
        es_docs = self._get_all_elasticsearch_docs([new_index])
        self.assertEqual(self.num_docs, es_docs['hits']['total'])
        es_alias = self._get_elasticsearch_aliases([new_index])
        self.assertEqual(1, len(es_alias))
        expected = {alias_listener: {}, alias_search: {}}
        self.assertEqual(es_alias[new_index]['aliases'], expected)

    def test_reindex_with_plugins(self):
        """Verify the reindexing functionality using both plugins to do the
        reindexing. We want to verify: the number of documents during reindex,
        the number of aliases during the reindex, the number of documents
        after the reindex and the aliases after the reindex.
        """
        alias_listener = self.role_plugin.alias_name_listener
        alias_search = self.role_plugin.alias_name_search
        resource_group = self.role_plugin.resource_group_name

        # Create a set of documents in ElasticSearch.
        self.create_es_documents(alias_listener)

        self.verify_initial_state()

        # Create and prepare a new index.
        new_index = es_utils.create_new_index(resource_group)
        self.role_plugin.prepare_index(index_name=new_index)
        self.non_role_plugin.prepare_index(index_name=new_index)

        # Set up the aliases.
        es_utils.setup_alias(new_index, alias_search, alias_listener)
        es_alias = self._get_elasticsearch_aliases([])
        self.assertEqual(2, len(es_alias))

        # Reindex using the plugins.
        self.role_plugin.index_initial_data()
        self.non_role_plugin.index_initial_data()
        self._flush_elasticsearch(alias_listener)

        self.verify_reindex_state(new_index)

        # Update aliases.
        old_index = es_utils.alias_search_update(alias_search, new_index)
        es_utils.delete_index(old_index)
        self._flush_elasticsearch(alias_listener)

        self.verify_new_alias_state(new_index=new_index,
                                    alias_search=alias_search,
                                    alias_listener=alias_listener)

    def test_reindex_with_es(self):
        """Verify the reindexing functionality using the elasticsearch reindex
        method to do the reindexing. We want to verify: the number of documents
        during reindex, the number of aliases during the reindex, the number of
        documents after the reindex and the aliases after the reindex.
        """
        alias_listener = self.role_plugin.alias_name_listener
        alias_search = self.role_plugin.alias_name_search
        resource_group = self.role_plugin.resource_group_name
        role_doc_type = self.role_plugin.document_type
        non_role_doc_type = self.non_role_plugin.document_type

        # Create a set of documents in ElasticSearch.
        self.create_es_documents(alias_listener)

        self.verify_initial_state()

        # Create and prepare a new index.
        new_index = es_utils.create_new_index(resource_group)
        self.role_plugin.prepare_index(index_name=new_index)
        self.non_role_plugin.prepare_index(index_name=new_index)

        # Set up the aliases.
        es_utils.setup_alias(new_index, alias_search, alias_listener)
        es_alias = self._get_elasticsearch_aliases([])
        self.assertEqual(2, len(es_alias))

        # Reindex using ElasticSearch.
        reindex = [role_doc_type, non_role_doc_type]
        es_utils.reindex(src_index=alias_listener, dst_index=new_index,
                         type_list=reindex)
        self._flush_elasticsearch(alias_listener)

        self.verify_reindex_state(new_index)

        # Update aliases.
        old_index = es_utils.alias_search_update(alias_search, new_index)
        es_utils.delete_index(old_index)
        self._flush_elasticsearch(alias_listener)

        self.verify_new_alias_state(new_index=new_index,
                                    alias_search=alias_search,
                                    alias_listener=alias_listener)

    def test_reindex_with_plugin_and_es(self):
        """Verify the reindexing functionality using both the plugin reindex
        and the elasticsearch reindex methods for the reindexing. We want to
        verify: the number of documents during reindex, the number of aliases
        during the reindex, the number of documents after the reindex and the
        aliases after the reindex.
        """
        alias_listener = self.role_plugin.alias_name_listener
        alias_search = self.role_plugin.alias_name_search
        resource_group = self.role_plugin.resource_group_name
        non_role_doc_type = self.non_role_plugin.document_type

        # Create a set of documents in ElasticSearch.
        self.create_es_documents(alias_listener)

        self.verify_initial_state()

        # Create and prepare a new index.
        new_index = es_utils.create_new_index(resource_group)
        self.role_plugin.prepare_index(index_name=new_index)
        self.non_role_plugin.prepare_index(index_name=new_index)

        # Set up the aliases.
        es_utils.setup_alias(new_index, alias_search, alias_listener)
        es_alias = self._get_elasticsearch_aliases([])
        self.assertEqual(2, len(es_alias))

        # Reindex. For role, use the plugin. For non-role use ElasticSearch.
        self.role_plugin.index_initial_data()
        reindex = [non_role_doc_type]
        es_utils.reindex(src_index=alias_listener, dst_index=new_index,
                         type_list=reindex)
        self._flush_elasticsearch(alias_listener)

        self.verify_reindex_state(new_index)

        # Update aliases.
        old_index = es_utils.alias_search_update(alias_search, new_index)
        es_utils.delete_index(old_index)
        self._flush_elasticsearch(alias_listener)

        self.verify_new_alias_state(new_index=new_index,
                                    alias_search=alias_search,
                                    alias_listener=alias_listener)
