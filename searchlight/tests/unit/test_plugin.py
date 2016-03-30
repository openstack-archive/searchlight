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
import six
import types

from oslo_config import cfg

from searchlight.common import exception
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import fake_plugins
import searchlight.tests.utils as test_utils


CONF = cfg.CONF


class TestPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestPlugin, self).setUp()

    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'IndexBase.mapping_use_doc_values',
                new_callable=mock.PropertyMock)
    def test_rbac_field_mapping(self, mock_use_doc_vals):
        mock_use_doc_vals.return_value = False
        mock_engine = mock.Mock()
        simple_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        simple_plugin.setup_index_mapping(index_name='fake')

        mock_engine.indices.put_mapping.assert_called_once_with(
            index='fake', doc_type='fake-simple',
            body={
                'properties': {
                    'id': {'type': 'string', 'index': 'not_analyzed'},
                    ROLE_USER_FIELD: {'include_in_all': False,
                                      'type': 'string',
                                      'index': 'not_analyzed'}
                }
            })

    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'IndexBase.mapping_use_doc_values',
                new_callable=mock.PropertyMock)
    def test_parent_child_mapping(self, mock_use_doc_vals):
        mock_use_doc_vals.return_value = False
        mock_engine = mock.Mock()

        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)

        child_plugin.register_parent(parent_plugin)

        parent_plugin.setup_index_mapping(index_name='fake')

        # Testing a couple of things; that
        expected_calls = [
            mock.call(
                index='fake',
                doc_type='fake-child',
                body={
                    '_parent': {'type': 'fake-simple'},
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'},
                        'parent_id': {'type': 'string',
                                      'index': 'not_analyzed'},
                        ROLE_USER_FIELD: {'include_in_all': False,
                                          'type': 'string',
                                          'index': 'not_analyzed'}
                    }
                }),
            mock.call(
                index='fake',
                doc_type='fake-simple',
                body={
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'},
                        ROLE_USER_FIELD: {'include_in_all': False,
                                          'type': 'string',
                                          'index': 'not_analyzed'}
                    }
                })
        ]
        mock_engine.indices.put_mapping.assert_has_calls(expected_calls)

        # Also test explicitly setting _parent on the child, which should
        # result in the same mapping
        mock_engine.reset_mock()
        mock_engine.indices.put_mapping.assert_not_called()

        child_mapping = child_plugin.get_mapping()

        # This mapping matches what would be assigned automatically
        def explicit_parent_mapping(_self):
            child_mapping['_parent'] = {'type': 'fake-simple'}
            return child_mapping

        child_plugin.get_mapping = types.MethodType(explicit_parent_mapping,
                                                    child_plugin)
        parent_plugin.setup_index_mapping(index_name='fake')

        mock_engine.indices.put_mapping.assert_has_calls(expected_calls)

    def test_invalid_parent_mapping(self):
        mock_engine = mock.Mock()

        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)

        child_plugin.register_parent(parent_plugin)

        child_mapping = child_plugin.get_mapping()

        def bad_parent_mapping(_self):
            child_mapping['_parent'] = {'type': 'this is not my parent'}
            return child_mapping

        # Now have the child's mapping include a bad _parent value
        child_plugin.get_mapping = types.MethodType(bad_parent_mapping,
                                                    child_plugin)
        expected_error = ("Mapping for 'fake-child' contains a _parent 'this "
                          "is not my parent' that doesn't match 'fake-simple'")
        self.assertRaisesRegexp(
            exception.IndexingException,
            expected_error,
            parent_plugin.setup_index_mapping,
            index_name='fake')

    def test_doc_values(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        test_doc_value_mapping = {
            'dynamic_templates': [
                {'test': {
                    "path_match": "test.*",
                    'mapping': {'type': 'integer'}
                }}
            ],
            'properties': {
                'not_analyzed_string': {'type': 'string',
                                        'index': 'not_analyzed'},
                'analyzed_string': {'type': 'string'},
                'sortable_string': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'no_doc_values': {'type': 'string', 'index': 'not_analyzed',
                                  'doc_values': False},
                'inttype': {'type': 'integer'},
                'datetype': {'type': 'date'},
                'booltype': {'type': 'boolean'},
                'shorttype': {'type': 'short'},
                'longtype': {'type': 'long'},
                'iptype': {'type': 'ip'},
                'nested': {
                    'type': 'nested',
                    'properties': {
                        'booltype': {'type': 'boolean'},
                        'analyzed_string': {'type': 'string'},
                        'not_analyzed_string': {'type': 'string',
                                                'index': 'not_analyzed'}
                    }
                }
            }
        }

        with mock.patch.object(plugin, 'get_mapping',
                               return_value=test_doc_value_mapping):
            # get_full_mapping is a generator
            doc_type, mapping = six.next(plugin.get_full_mapping())
            props = mapping['properties']

            # These fields should all have doc_values. Explicitly testing
            # for 'true' here rather than assertTrue
            for field in ('not_analyzed_string', 'inttype', 'datetype',
                          'booltype', 'shorttype', 'longtype'):
                self.assertEqual(True, props[field]['doc_values'])

            self.assertEqual(
                True, props['sortable_string']['fields']['raw']['doc_values'])

            # Check nested
            for field in ('booltype', 'not_analyzed_string'):
                self.assertEqual(
                    True, props['nested']['properties'][field]['doc_values'])

            # Check dynamic templates
            dyn_mapping = mapping['dynamic_templates'][0]['test']['mapping']
            self.assertEqual(True, dyn_mapping['doc_values'])

            # These should not have doc_values
            self.assertNotIn('doc_values', props['analyzed_string'])
            self.assertNotIn('doc_values',
                             props['nested']['properties']['analyzed_string'])

            # Test explicit setting of doc_values
            self.assertEqual(False, props['no_doc_values']['doc_values'])

    def test_rbac_field_doc_values(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        doc_Type, mapping = six.next(plugin.get_full_mapping())
        props = mapping['properties']
        self.assertEqual(True, props[ROLE_USER_FIELD]['doc_values'])

    def test_doc_values_property(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        doc_type, mapping = six.next(plugin.get_full_mapping())
        self.assertEqual(True, mapping['properties']['id']['doc_values'])

        # Test the same but disabling doc values for the plugin
        with mock.patch.object(plugin.__class__,
                               'mapping_use_doc_values',
                               new_callable=mock.PropertyMock) as conf_mock:
            conf_mock.return_value = False
            doc_type, mapping = six.next(plugin.get_full_mapping())
            self.assertNotIn('doc_values', mapping['properties']['id'])

    def test_setup_index_settings(self):
        mock_engine = mock.Mock()

        # Test #1: Use the default settings for the plugin.
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        plugin.setup_index_settings(index_name='fake')
        mock_engine.indices.put_settings.assert_called_once_with(
            index='fake',
            body={
                'index': {
                    'gc_deletes': '300s'
                }
            })

        # Test #2: The plugin has no settings.
        mock_engine.reset_mock()
        with mock.patch.object(plugin, 'get_settings', return_value=None):
            plugin.setup_index_settings(index_name='fake')
            mock_engine.indices.put_settings.assert_not_called()

    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'IndexBase.setup_index_mapping')
    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'IndexBase.setup_index_settings')
    def test_prepare_index(self, mock_settings, mock_mapping):
        """Verify Indexbase.prepare_index(). The method will verify that all
        non-analyzed mapping fields that are raw, are truly marked as raw.
        This applies to any children plugins. There should not be any
        exceptions raised. In addition, the index mappings and settings are
        created at this time. Since we have separate unit tests for verifying
        the index mappings and index settings functionality, we will verify
        only that these methods are called.
        """
        mock_engine = mock.Mock()

        # Test #1: Plugin with no children, good "raw" mapping field.
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        with mock.patch.object(plugin, 'get_mapping') as mock_map:
            mock_map.return_value = {"properties": {
                "id": {"type": "string", "index": "not_analyzed"},
                "name": {"type": "string", "fields": {
                    "raw": {"type": "string", "index": "not_analyzed"}
                }}}}

            plugin.prepare_index('fake')
            mock_settings.assert_called_once_with(index_name='fake')
            mock_mapping.assert_called_once_with(index_name='fake')

        # Test #2: Plugin with no children, bad "raw" mapping field.
        mock_mapping.reset_mock()
        mock_settings.reset_mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        with mock.patch.object(plugin, 'get_mapping') as mock_map:
            mock_map.return_value = {"properties": {
                "id": {"type": "string", "index": "not_analyzed"},
                "name": {"type": "string"}}}

            message = ("Field 'name' for searchlight-listener/fake-simple "
                       "must contain a subfield whose name is 'raw' for "
                       "sorting.")
            self.assertRaisesRegexp(Exception, message,
                                    plugin.prepare_index, index_name='fake')
            mock_settings.assert_not_called()
            mock_mapping.assert_not_called()

        # Test #3: Plugin with two children. No "raw" mapping fields.
        mock_mapping.reset_mock()
        mock_settings.reset_mock()
        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child1_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        child1_plugin.register_parent(parent_plugin)
        child2_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        child2_plugin.register_parent(parent_plugin)
        parent_plugin.prepare_index('fake')
        mock_settings.assert_called_once_with(index_name='fake')
        mock_mapping.assert_called_once_with(index_name='fake')

    @mock.patch('searchlight.elasticsearch.plugins.helper.'
                'IndexingHelper.save_documents')
    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'NotificationBase.get_version')
    def test_initial_indexing(self, mock_vers, mock_save):
        mock_engine = mock.Mock()

        # Test #1: Index with two documents.
        mock_vers.return_value = '1234'
        plugin = fake_plugins.NonRoleSeparatedPlugin(es_engine=mock_engine)
        plugin.initial_indexing(index_name='fake')
        mock_save.assert_called_once_with(fake_plugins.NON_ROLE_SEPARATED_DATA,
                                          versions=['1234', '1234'],
                                          index='fake')

        # Test #2: Do not index any documents.
        mock_save.reset_mock()
        plugin.initial_indexing(index_name='fake', setup_data=False)
        mock_save.assert_not_called()
