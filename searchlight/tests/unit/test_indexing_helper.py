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

import mock

from searchlight.elasticsearch.plugins import utils as plugin_utils
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
        indexing_helper = plugin_utils.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.utils.helpers.bulk'
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
        self.assertTrue('public_field' in fake1_admin)
        self.assertTrue('admin_wildcard_this' in fake1_admin)
        self.assertEqual('admin', fake1_admin[ROLE_USER_FIELD])

        fake1_user = list(filter(lambda a: a['_id'] == 'role-fake1_USER',
                                 actions))[0]['_source']
        self.assertEqual('role-fake1', fake1_user['id'])
        self.assertTrue('public_field' in fake1_user)
        self.assertFalse('admin_wildcard_this' in fake1_user)
        self.assertFalse('admin_specific' in fake1_user)
        self.assertEqual('user', fake1_user[ROLE_USER_FIELD])

    def test_non_role_separated_save_docs(self):
        """Test that for a plugin that doesn't specify any protected fields,
        ids are left alone and there's only one copy of each indexed doc
        """
        mock_engine = mock.Mock()
        plugin = fake_plugins.NonRoleSeparatedPlugin(es_engine=mock_engine)
        indexing_helper = plugin_utils.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.utils.helpers.bulk'
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

    def test_role_separated_delete(self):
        """Test that deletion for a role-separated plugin deletes both docs"""
        mock_engine = mock.Mock()
        plugin = fake_plugins.RoleSeparatedPlugin(es_engine=mock_engine)
        indexing_helper = plugin_utils.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.utils.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.delete_document_by_id('role-fake1')

            expected_delete_actions = [
                {'_op_type': 'delete',
                 '_id': 'role-fake1_ADMIN'},
                {'_op_type': 'delete',
                 '_id': 'role-fake1_USER'}
            ]
            mock_bulk.assert_called_once_with(
                client=plugin.engine,
                index=plugin.index_name,
                doc_type=plugin.document_type,
                actions=expected_delete_actions)

    def test_non_role_separated_delete(self):
        """Test that deletion for a role-separated plugin deletes both docs"""
        mock_engine = mock.Mock()
        plugin = fake_plugins.NonRoleSeparatedPlugin(es_engine=mock_engine)
        indexing_helper = plugin_utils.IndexingHelper(plugin)

        bulk_name = 'searchlight.elasticsearch.plugins.utils.helpers.bulk'
        with mock.patch(bulk_name) as mock_bulk:
            indexing_helper.delete_document_by_id('non-role-fake1')

            expected_delete_actions = [
                {'_op_type': 'delete',
                 '_id': 'non-role-fake1'}
            ]
            mock_bulk.assert_called_once_with(
                client=plugin.engine,
                index=plugin.index_name,
                doc_type=plugin.document_type,
                actions=expected_delete_actions)

    def test_delete_children_role_separated(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSeparatedChildPlugin(es_engine=mock_engine)
        indexing_helper = plugin_utils.IndexingHelper(plugin)

        scan_name = 'searchlight.elasticsearch.plugins.utils.helpers.scan'
        bulk_name = 'searchlight.elasticsearch.plugins.utils.helpers.bulk'

        mock_scan_data = [
            {'_id': '1_ADMIN', 'fields': {'_parent': 'p1_ADMIN'}},
            {'_id': '1_USER', 'fields': {'_parent': 'p1_USER'}}
        ]
        with mock.patch(scan_name, return_value=mock_scan_data) as mock_scan:
            with mock.patch(bulk_name) as mock_bulk:
                indexing_helper.delete_documents_with_parent('p1')

                parent_type = plugin.parent_plugin_type()
                base_full_parent_type = '%s#%s' % (parent_type, 'p1')
                expected_scan_query = {
                    'fields': ['_parent'],
                    'query': {
                        'term': {
                            '_parent': [base_full_parent_type + '_ADMIN',
                                        base_full_parent_type + '_USER']
                        }
                    }
                }
                mock_scan.assert_called_with(
                    client=plugin.engine,
                    index=plugin.index_name,
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
                    index=plugin.index_name,
                    doc_type=plugin.document_type,
                    actions=expected_delete_actions
                )

    def test_delete_children_non_role_separated(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        indexing_helper = plugin_utils.IndexingHelper(plugin)

        scan_name = 'searchlight.elasticsearch.plugins.utils.helpers.scan'
        bulk_name = 'searchlight.elasticsearch.plugins.utils.helpers.bulk'

        mock_scan_data = [
            {'_id': '1', 'fields': {'_parent': 'p1'}},
        ]
        with mock.patch(scan_name, return_value=mock_scan_data) as mock_scan:
            with mock.patch(bulk_name) as mock_bulk:
                indexing_helper.delete_documents_with_parent('p1')

                parent_type = plugin.parent_plugin_type()
                expected_scan_query = {
                    'fields': ['_parent'],
                    'query': {
                        'term': {
                            '_parent': '%s#%s' % (parent_type, 'p1')
                        }
                    }
                }
                mock_scan.assert_called_with(
                    client=plugin.engine,
                    index=plugin.index_name,
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
                    index=plugin.index_name,
                    doc_type=plugin.document_type,
                    actions=expected_delete_actions
                )
