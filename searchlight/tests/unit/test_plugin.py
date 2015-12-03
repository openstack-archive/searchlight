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
