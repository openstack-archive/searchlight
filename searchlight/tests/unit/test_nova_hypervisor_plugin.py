#    Copyright (c) 2016 Kylin Cloud
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

import datetime
from unittest import mock

import novaclient.v2.hypervisors as novaclient_hypervisors

from searchlight.elasticsearch.plugins.nova import\
    hypervisors as hypervisors_plugin
import searchlight.tests.utils as test_utils


_now = datetime.datetime.utcnow()
updated_now = _now.strftime('%Y-%m-%dT%H:%M:%SZ')


def _hypervisor_fixture(hypervisor_id, **kwargs):
    attrs = {
        'status': 'enabled',
        'service': {
            'host': 'test',
            'disabled_reason': None,
            'id': 7
        },
        'vcpus_used': 20,
        'hypervisor_type': 'fake',
        'free_ram_mb': 799288,
        'local_gb_used': 0,
        'host_ip': '127.0.0.1',
        'id': hypervisor_id,
        'memory_mb': 800000,
        'current_workload': 0,
        'vcpus': 1000,
        'state': 'up',
        'running_vms': 20,
        'free_disk_gb': 600000,
        'hypervisor_version': 1000,
        'disk_available_least': 0,
        'local_gb': 600000,
        'cpu_info': '{"arch": "x86_64", "model": "Nehalem",'
                    '"vendor": "Intel", "features": ["pge", "clflush"],'
                    '"topology": {"cores": 1, "threads": 1, "sockets": 4}}',
        'memory_mb_used': 712
    }

    attrs.update(kwargs)
    hypervisor = mock.Mock(spec=novaclient_hypervisors.Hypervisor, **attrs)
    hypervisor.to_dict.return_value = attrs
    return hypervisor


class TestHypervisorLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestHypervisorLoaderPlugin, self).setUp()
        self.plugin = hypervisors_plugin.HypervisorIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.hypervisor1 = _hypervisor_fixture(
            '1', hypervisor_hostname="host1")

    def test_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Nova::Hypervisor',
                         self.plugin.get_document_type())

    def test_serialize(self):
        expected = {
            'cpu_info': {
                u'arch': u'x86_64',
                u'features': [u'pge', u'clflush'],
                u'model': u'Nehalem',
                u'topology': {u'cores': 1, u'sockets': 4, u'threads': 1},
                u'vendor': u'Intel'},
            'disk_available_least': 0,
            'host_ip': '127.0.0.1',
            'hypervisor_hostname': 'host1',
            'hypervisor_type': 'fake',
            'hypervisor_version': 1000,
            'id': '1',
            'local_gb': 600000,
            'memory_mb': 800000,
            'service': {'disabled_reason': None, 'host': 'test', 'id': 7},
            'state': 'up',
            'status': 'enabled',
            'updated_at': updated_now,
            'vcpus': 1000,
        }
        with mock.patch('searchlight.elasticsearch.plugins.utils.get_now_str',
                        return_value=updated_now):
            serialized = self.plugin.serialize(self.hypervisor1)
        self.assertEqual(expected, serialized)
