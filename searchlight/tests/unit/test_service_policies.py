# Copyright (c) 2016 Hewlett-Packard Enterprise Development L.P.
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

import os
from unittest import mock

from oslo_config import cfg
from searchlight import service_policies
import searchlight.tests.utils as test_utils


CONF = cfg.CONF


class TestServicePolicies(test_utils.BaseTestCase):
    def setUp(self):
        super(TestServicePolicies, self).setUp()

    def test_get_enforcers_abs_path(self):
        """Test service policy creation from cfg.policy_files"""

        nova_path = os.path.join(self.conf_dir, 'nova.json')
        with open(nova_path, 'w') as nova_policy_file:
            nova_policy_file.write('{"test": ""}')

        with mock.patch.object(CONF, 'service_policies') as mock_serv_pols:
            mock_serv_pols.service_policy_files = {'compute': nova_path}
            mock_serv_pols.service_policy_path = ''

            enforcers = service_policies._get_enforcers()
            self.assertEqual(['compute'], list(enforcers.keys()))
            self.assertEqual(['test'], list(enforcers['compute'].rules.keys()))

            # Check that get_enforcer_for_service works as expected
            self.assertIs(service_policies.get_enforcer_for_service('compute'),
                          enforcers['compute'])
            self.assertIsNone(service_policies.get_enforcer_for_service('aa'))

    def test_get_enforcers_base_path(self):
        """Test service policy creation with cfg.policy_path set"""
        nova_path = os.path.join(self.conf_dir, 'nova.json')
        with open(nova_path, 'w') as nova_policy_file:
            nova_policy_file.write('{"test": ""}')

        with mock.patch.object(CONF, 'service_policies') as mock_serv_pols:
            mock_serv_pols.service_policy_files = {'compute': 'nova.json'}
            mock_serv_pols.service_policy_path = self.conf_dir

            enforcers = service_policies._get_enforcers()
            self.assertEqual(['compute'], list(enforcers.keys()))
            self.assertEqual(['test'], list(enforcers['compute'].rules.keys()))

            # Check that get_enforcer_for_service works as expected
            self.assertIs(service_policies.get_enforcer_for_service('compute'),
                          enforcers['compute'])
            self.assertIsNone(service_policies.get_enforcer_for_service('aa'))
