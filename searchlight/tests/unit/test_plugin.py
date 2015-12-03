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
import types

from searchlight.common import exception
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import fake_plugins
import searchlight.tests.utils as test_utils


class TestPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestPlugin, self).setUp()

    def test_rbac_field_mapping(self):
        mock_engine = mock.Mock()
        simple_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        simple_plugin.setup_mapping()

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

    def test_parent_child_mapping(self):
        mock_engine = mock.Mock()

        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)

        child_plugin.register_parent(parent_plugin)

        parent_plugin.setup_mapping()

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
        parent_plugin.setup_mapping()

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
            parent_plugin.setup_mapping)
