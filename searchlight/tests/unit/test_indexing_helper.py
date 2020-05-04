# Copyright 2016 Hewlett-Packard Corporation
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

import copy
from elasticsearch import exceptions as es_exceptions
from oslo_config import cfg
from unittest import mock

from searchlight.elasticsearch.plugins import helper
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import fake_plugins
from searchlight.tests import utils as test_utils


class TestIndexingHelper(test_utils.BaseTestCase):
    def test_role_separated_save_docs(self):
        """Test admin only fields are correctly removed from serialization
        and that alternate _id values are used
        """
        mock_engine = mock.Mock()
        plugin = fake_plugins.RoleSeparatedPlugin(es_engine=mock_engine)
        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            count = len(plugin.get_objects())
            fake_versions = range(1, count + 1)
            indexing_helper.save_documents(plugin.get_objects(), fake_versions)
            self.assertEqual(1, len(mock_bulk.call_args_list))
            actions = list(mock_bulk.call_args_list[0][1]['actions'])

        self.assertEqual(4, len(actions))
        self.assertEqual(set(['role-fake1_ADMIN', 'role-fake2_ADMIN',
                             'role-fake1_USER', 'role-fake2_USER']),
                         set(action['_id'] for action in actions))
        self.assertEqual(set(fake_versions),
                         set(action['_version'] for action in actions))
        self.assertEqual(['external'] * 4,
                         [action['_version_type'] for action in actions])
        # This plugin filters on admin_wildcard_* and admin_specific
        fake1_admin = list(filter(lambda a: a['_id'] == 'role-fake1_ADMIN',
                                  actions))[0]['_source']
        self.assertEqual('role-fake1', fake1_admin['id'])
        self.assertIn('public_field', fake1_admin)
        self.assertIn('admin_wildcard_this', fake1_admin)
        self.assertEqual('admin', fake1_admin[ROLE_USER_FIELD])

        fake1_user = list(filter(lambda a: a['_id'] == 'role-fake1_USER',
                                 actions))[0]['_source']
        self.assertEqual('role-fake1', fake1_user['id'])
        self.assertIn('public_field', fake1_user)
        self.assertNotIn('admin_wildcard_this', fake1_user)
        self.assertNotIn('admin_specific', fake1_user)
        self.assertEqual('user', fake1_user[ROLE_USER_FIELD])

    def test_non_role_separated_save_docs(self):
        """Test that for a plugin that doesn't specify any protected fields,
        ids are left alone and there's only one copy of each indexed doc
        """
        mock_engine = mock.Mock()
        plugin = fake_plugins.NonRoleSeparatedPlugin(es_engine=mock_engine)
        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            count = len(plugin.get_objects())
            fake_versions = range(1, count + 1)
            indexing_helper.save_documents(plugin.get_objects(), fake_versions)
            self.assertEqual(1, len(mock_bulk.call_args_list))
            actions = list(mock_bulk.call_args_list[0][1]['actions'])

        self.assertEqual(2, len(actions))
        self.assertEqual(set(['non-role-fake1', 'non-role-fake2']),
                         set(action['_id'] for action in actions))
        self.assertEqual(set(fake_versions),
                         set(action['_version'] for action in actions))
        self.assertEqual(['external'] * 2,
                         [action['_version_type'] for action in actions])
        fake1 = actions[0]['_source']
        self.assertEqual(['admin', 'user'],
                         sorted(fake1.pop(ROLE_USER_FIELD)))
        self.assertEqual(fake_plugins.NON_ROLE_SEPARATED_DATA[0],
                         actions[0]['_source'])

    @mock.patch('searchlight.elasticsearch.plugins.helper.helpers.bulk')
    @mock.patch.object(cfg.CONF, 'resource_plugin')
    @mock.patch.object(cfg.CONF, 'service_credentials')
    def test_region_mapping(self, service_credentials_conf,
                            resource_plugin_conf, mock_bulk):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        resource_plugin_conf.include_region_name = True
        service_credentials_conf.os_region_name = 'test-region'

        indexing_helper = helper.IndexingHelper(plugin)

        _, mapping = next(plugin.get_full_mapping())
        self.assertIn('region_name', mapping['properties'])

        count = len(plugin.get_objects())
        fake_versions = range(1, count + 1)
        indexing_helper.save_documents(plugin.get_objects(),
                                       fake_versions)

        self.assertEqual(1, len(mock_bulk.call_args_list))
        actions = list(mock_bulk.call_args_list[0][1]['actions'])
        self.assertEqual(['test-region'],
                         actions[0]['_source']['region_name'])

        # Test without a region
        resource_plugin_conf.include_region_name = False
        mock_bulk.reset_mock()

        _, mapping = next(plugin.get_full_mapping())
        self.assertNotIn('region_name', mapping['properties'])
        indexing_helper.save_documents(plugin.get_objects(),
                                       fake_versions)
        actions = list(mock_bulk.call_args_list[0][1]['actions'])
        self.assertNotIn('region_name', actions[0]['_source'])

    def test_role_separated_delete(self):
        """Test that deletion for a role-separated plugin deletes both docs"""
        mock_engine = mock.Mock()
        plugin = fake_plugins.RoleSeparatedPlugin(es_engine=mock_engine)
        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.delete_document({'_id': 'role-fake1'})

            expected_delete_actions = [
                {'_op_type': 'delete',
                 '_id': 'role-fake1_ADMIN'},
                {'_op_type': 'delete',
                 '_id': 'role-fake1_USER'}
            ]
            mock_bulk.assert_called_once_with(
                client=plugin.engine,
                index=plugin.alias_name_listener,
                doc_type=plugin.document_type,
                actions=expected_delete_actions)

    def test_non_role_separated_delete(self):
        """Test that deletion for a role-separated plugin deletes the doc"""
        mock_engine = mock.Mock()
        plugin = fake_plugins.NonRoleSeparatedPlugin(es_engine=mock_engine)
        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.delete_document({'_id': 'non-role-fake1'})

            expected_delete_actions = [
                {'_op_type': 'delete',
                 '_id': 'non-role-fake1'}
            ]
            mock_bulk.assert_called_once_with(
                client=plugin.engine,
                index=plugin.alias_name_listener,
                doc_type=plugin.document_type,
                actions=expected_delete_actions)

    def test_save_child_parent_both_separated(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSeparatedChildPlugin(es_engine=mock_engine)
        parent_plugin = fake_plugins.RoleSeparatedPlugin(es_engine=mock_engine)
        plugin.register_parent(parent_plugin)

        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'

        child_docs = copy.deepcopy(fake_plugins.CHILD_DATA)

        # First run where both child and parent are role-separated (and thus
        # we'd expect two copies of both parent and child with appropriate
        # ids linking them)
        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.save_documents(child_docs)

            self.assertEqual(1, len(mock_bulk.call_args_list))
            actions = list(mock_bulk.call_args_list[0][1]['actions'])

        expected_admin_doc = copy.deepcopy(child_docs[0])
        expected_admin_doc[ROLE_USER_FIELD] = 'admin'
        expected_user_doc = copy.deepcopy(child_docs[0])
        expected_user_doc[ROLE_USER_FIELD] = 'user'

        expected_actions = [
            {'_op_type': 'index', '_id': 'child1_ADMIN',
             '_source': expected_admin_doc, '_parent': 'simple1_ADMIN'},
            {'_op_type': 'index', '_id': 'child1_USER',
             '_source': expected_user_doc, '_parent': 'simple1_USER'}
        ]

        self.assertEqual(expected_actions, list(actions))

    @mock.patch.object(fake_plugins.FakeSeparatedChildPlugin,
                       'requires_role_separation',
                       new_callable=mock.PropertyMock)
    def test_save_parent_only_separated(self, mock_role_separated):
        """Test where the parent document is role separated but this child
        is not; it's expected the parent's _USER documents be used for _parent
        """
        mock_role_separated.return_value = False

        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSeparatedChildPlugin(es_engine=mock_engine)
        parent_plugin = fake_plugins.RoleSeparatedPlugin(es_engine=mock_engine)
        plugin.register_parent(parent_plugin)

        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'

        child_docs = copy.deepcopy(fake_plugins.CHILD_DATA)

        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.save_documents(child_docs)

            self.assertEqual(1, len(mock_bulk.call_args_list))
            actions = list(mock_bulk.call_args_list[0][1]['actions'])

        expected_doc = copy.deepcopy(child_docs[0])
        expected_doc[ROLE_USER_FIELD] = ['user', 'admin']

        expected_actions = [
            {'_op_type': 'index', '_id': 'child1',
             '_source': expected_doc, '_parent': 'simple1_USER'},
        ]

        self.assertEqual(expected_actions, list(actions))

    @mock.patch.object(fake_plugins.FakeChildPlugin,
                       'requires_role_separation',
                       new_callable=mock.PropertyMock)
    def test_child_only_separated(self, mock_role_separated):
        """Test where the child (and not the parent) is separated. Expect
        two documents with the same parent
        """
        mock_role_separated.return_value = True

        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        plugin.register_parent(parent_plugin)

        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'

        child_docs = copy.deepcopy(fake_plugins.CHILD_DATA)

        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.save_documents(child_docs)

            self.assertEqual(1, len(mock_bulk.call_args_list))
            actions = list(mock_bulk.call_args_list[0][1]['actions'])

        expected_admin_doc = copy.deepcopy(child_docs[0])
        expected_admin_doc[ROLE_USER_FIELD] = 'admin'
        expected_user_doc = copy.deepcopy(child_docs[0])
        expected_user_doc[ROLE_USER_FIELD] = 'user'

        expected_actions = [
            {'_op_type': 'index', '_id': 'child1_ADMIN',
             '_source': expected_admin_doc, '_parent': 'simple1'},
            {'_op_type': 'index', '_id': 'child1_USER',
             '_source': expected_user_doc, '_parent': 'simple1'}
        ]
        self.assertEqual(expected_actions, list(actions))

    def test_delete_children_role_separated(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSeparatedChildPlugin(es_engine=mock_engine)
        parent_plugin = fake_plugins.RoleSeparatedPlugin(es_engine=mock_engine)
        plugin.register_parent(parent_plugin)

        indexing_helper = helper.IndexingHelper(plugin)

        scan_name = 'searchlight.elasticsearch.plugins.helper.helpers.scan'
        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'

        mock_scan_data = [
            {'_id': '1_ADMIN',
             'fields': {'_parent': 'p1_ADMIN'}},
            {'_id': '1_USER',
             'fields': {'_parent': 'p1_USER'}}
        ]
        with mock.patch(scan_name, return_value=mock_scan_data) as mock_scan:
            with mock.patch(bulk_name) as mock_bulk:
                indexing_helper.delete_documents_with_parent('p1')

                parent_type = plugin.parent_plugin_type()
                base_full_parent_type = '%s#%s' % (parent_type, 'p1')
                expected_scan_query = {
                    'fields': ['_parent', '_routing'],
                    'query': {
                        'terms': {
                            '_parent': [base_full_parent_type + '_ADMIN',
                                        base_full_parent_type + '_USER']
                        }
                    }
                }
                mock_scan.assert_called_with(
                    client=plugin.engine,
                    index=plugin.alias_name_listener,
                    doc_type=plugin.document_type,
                    query=expected_scan_query
                )

                expected_delete_actions = [
                    {'_op_type': 'delete',
                     '_id': '1_ADMIN',
                     '_parent': 'p1_ADMIN'},
                    {'_op_type': 'delete',
                     '_id': '1_USER',
                     '_parent': 'p1_USER'}
                ]
                mock_bulk.assert_called_with(
                    client=plugin.engine,
                    index=plugin.alias_name_listener,
                    doc_type=plugin.document_type,
                    actions=expected_delete_actions
                )

    def test_delete_children_non_role_separated(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        plugin.register_parent(parent_plugin)
        indexing_helper = helper.IndexingHelper(plugin)

        scan_name = 'searchlight.elasticsearch.plugins.helper.helpers.scan'
        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'

        mock_scan_data = [
            {'_id': '1',
             'fields': {'_parent': 'p1'}},
        ]
        with mock.patch(scan_name, return_value=mock_scan_data) as mock_scan:
            with mock.patch(bulk_name) as mock_bulk:
                indexing_helper.delete_documents_with_parent('p1')

                parent_type = plugin.parent_plugin_type()
                expected_scan_query = {
                    'fields': ['_parent', '_routing'],
                    'query': {
                        'term': {
                            '_parent': '%s#%s' % (parent_type, 'p1')
                        }
                    }
                }
                mock_scan.assert_called_with(
                    client=plugin.engine,
                    index=plugin.alias_name_listener,
                    doc_type=plugin.document_type,
                    query=expected_scan_query
                )

                expected_delete_actions = [
                    {'_op_type': 'delete',
                     '_id': '1',
                     '_parent': 'p1'}
                ]
                mock_bulk.assert_called_with(
                    client=plugin.engine,
                    index=plugin.alias_name_listener,
                    doc_type=plugin.document_type,
                    actions=expected_delete_actions
                )

    def test_routing_save_docs(self):
        """Test that for a plugin that specifies routing_id field will
        end up with "_routing" set while indexing.
        """
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimpleRoutingPlugin(es_engine=mock_engine)
        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            count = len(plugin.get_objects())
            fake_versions = range(1, count + 1)
            indexing_helper.save_documents(plugin.get_objects(), fake_versions)
            self.assertEqual(1, len(mock_bulk.call_args_list))
            actions = list(mock_bulk.call_args_list[0][1]['actions'])

        # '_routing' is added to action only if set in the plugin property
        # FakeSimpleRoutingPlugin has it defined.
        self.assertIs(True, '_routing' in actions[0])
        self.assertEqual('tenant1', actions[0]['_routing'])

    def test_routing_delete(self):
        """Test that deletion for a routing based plugin deletes docs"""
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimpleRoutingPlugin(es_engine=mock_engine)
        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.delete_document(
                {'_id': 'id_for_routing_plugin-fake1',
                 '_routing': 'tenant1'})

            expected_delete_actions = [
                {'_op_type': 'delete',
                 '_id': 'id_for_routing_plugin-fake1',
                 '_routing': 'tenant1'}
            ]
            mock_bulk.assert_called_once_with(
                client=plugin.engine,
                index=plugin.alias_name_listener,
                doc_type=plugin.document_type,
                actions=expected_delete_actions)

    def test_bulk_index_error_handling(self):
        """Check that 404 and 409 errors are appropriately ignored"""
        from elasticsearch import helpers

        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        indexing_helper = helper.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.helper.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            mock_bulk.side_effect = helpers.BulkIndexError(
                "1 document(s) failed to index",
                [{'delete': {"_id": "1", "error": "Some error", "status": 404,
                             "exception": helpers.TransportError()}}]
            )

            indexing_helper.delete_documents([{'_id': '1'}])

            self.assertEqual(1, mock_bulk.call_count)

        with mock.patch(bulk_name) as mock_bulk:
            mock_bulk.side_effect = helpers.BulkIndexError(
                "1 document(s) failed to index",
                [{'index': {"_id": "1",
                            "error": {
                                "type": "version_conflict_engine_exception"},
                            "status": 409}}]
            )
            indexing_helper.save_documents([{'id': '1'}])
            self.assertEqual(1, mock_bulk.call_count)

    def test_multiple_alias_exception_detection(self):
        alias_exc = es_exceptions.RequestError(
            400, "Something " + helper.ALIAS_EXCEPTION_STRING, {})
        self.assertTrue(helper._is_multiple_alias_exception(alias_exc))

        other_exc = Exception("Blah blah")
        self.assertFalse(helper._is_multiple_alias_exception(other_exc))

    def test_multiple_alias_exception_elasticsearch2(self):
        # The es-2 format is different
        alias_exc = es_exceptions.RequestError(
            400,
            'illegal_argument_exception',
            {"error": {
                "root_cause": [{
                    "type": "illegal_argument_exception",
                    "reason": "Something " + helper.ALIAS_EXCEPTION_STRING
                }],
                "type": "illegal_argument_exception",
                "reason": "Something " + helper.ALIAS_EXCEPTION_STRING
            }})
        self.assertTrue(helper._is_multiple_alias_exception(alias_exc))

    def test_strip_suffix(self):
        _id = 'aaaa-bbbb'
        admin_id = _id + helper.ADMIN_ID_SUFFIX
        user_id = _id + helper.USER_ID_SUFFIX

        # Test does nothing if there's nothing to do
        self.assertEqual(
            _id,
            helper.strip_role_suffix(_id))
        self.assertEqual(
            _id,
            helper.strip_role_suffix(_id, helper.ADMIN_ID_SUFFIX))

        # Test when there is something to do
        self.assertEqual(
            _id,
            helper.strip_role_suffix(admin_id, helper.ADMIN_ID_SUFFIX))
        self.assertEqual(
            _id,
            helper.strip_role_suffix(user_id, helper.USER_ID_SUFFIX))
        self.assertEqual(_id, helper.strip_role_suffix(user_id))
        self.assertEqual(_id, helper.strip_role_suffix(user_id))

        # Test mismatches
        self.assertEqual(
            admin_id,
            helper.strip_role_suffix(admin_id, helper.USER_ID_SUFFIX))
        self.assertEqual(
            user_id,
            helper.strip_role_suffix(user_id, helper.ADMIN_ID_SUFFIX))

    def test_delete_unknown_parent(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSeparatedChildPlugin(es_engine=mock_engine)
        doc_id = 'aaaa-bbbb'
        parent_id = '1111-2222'

        # Mock the delete function because the internals are tested elsewhere
        # First test with parent and routing
        with mock.patch.object(plugin.index_helper,
                               'delete_document') as mock_del:
            mock_engine.search.return_value = {
                'hits': {
                    'total': 1,
                    'hits': [{'_id': doc_id + helper.ADMIN_ID_SUFFIX,
                              '_routing': parent_id,
                              '_parent': parent_id + helper.ADMIN_ID_SUFFIX}]
                }
            }
            plugin.index_helper.delete_document_unknown_parent(doc_id)
            mock_del.assert_called_with({'_id': doc_id,
                                         '_parent': parent_id,
                                         '_routing': parent_id})

        # Now no explicit routing
        with mock.patch.object(plugin.index_helper,
                               'delete_document') as mock_del:
            mock_engine.search.return_value = {
                'hits': {
                    'total': 1,
                    'hits': [{'_id': doc_id + helper.ADMIN_ID_SUFFIX,
                              '_parent': parent_id + helper.ADMIN_ID_SUFFIX}]
                }
            }
            plugin.index_helper.delete_document_unknown_parent(doc_id)
            mock_del.assert_called_with({'_id': doc_id,
                                         '_parent': parent_id})

        # Test no results found
        with mock.patch.object(plugin.index_helper,
                               'delete_document') as mock_del:
            mock_engine.search.return_value = {
                'hits': {
                    'total': 0,
                    'hits': []
                }
            }
            plugin.index_helper.delete_document_unknown_parent(doc_id)
            self.assertEqual(0, mock_del.call_count)

        # Also test a non-separated plugin
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        with mock.patch.object(plugin.index_helper,
                               'delete_document') as mock_del:
            mock_engine.search.return_value = {
                'hits': {
                    'total': 1,
                    'hits': [{'_id': doc_id,
                              '_parent': parent_id}]
                }
            }
            plugin.index_helper.delete_document_unknown_parent(doc_id)
            mock_del.assert_called_with({'_id': doc_id,
                                         '_parent': parent_id})
