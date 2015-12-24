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

from searchlight.tests import functional
from searchlight.tests import utils

TENANT1 = u"1816a16093df465dbc609cf638422a05"


class TestNovaPlugins(functional.FunctionalTest):
    def setUp(self):
        super(TestNovaPlugins, self).setUp()
        self.hyper_plugin = self.initialized_plugins['OS::Nova::Hypervisor']
        self.hyper_objects = self._load_fixture_data('load/hypervisors.json')

    def test_hypervisor_rbac(self):
        self._index(self.hyper_plugin,
                    [utils.DictObj(**hyper) for hyper in self.hyper_objects])
        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "all_projects": True},
            TENANT1, role="admin")
        self.assertEqual(200, response.status)
        self.assertEqual(2, json_content['hits']['total'])

        hits = json_content['hits']['hits']
        expected_sources = [{
            u'cpu_info': {u'arch': u'x86_64',
                          u'features': [u'pge', u'clflush'],
                          u'model': u'Nehalem',
                          u'topology': {u'cores': 20,
                                        u'sockets': 4,
                                        u'threads': 1},
                          u'vendor': u'Intel'},
            u'disk_available_least': 0,
            u'host_ip': u'192.168.1.11',
            u'hypervisor_hostname': u'host1',
            u'hypervisor_type': u'fake',
            u'hypervisor_version': 1000,
            u'id': u'1',
            u'local_gb': 600000,
            u'memory_mb': 800000,
            u'service': {u'disabled_reason': None,
                         u'host': u'host1',
                         u'id': 7},
            u'state': u'up',
            u'status': u'enabled',
            u'vcpus': 1000},
            {u'cpu_info': {u'arch': u'x86_64',
                           u'features': [u'pge', u'clflush'],
                           u'model': u'Nehalem',
                           u'topology': {u'cores': 10,
                                         u'sockets': 4,
                                         u'threads': 1},
                           u'vendor': u'Intel'},
             u'disk_available_least': 0,
             u'host_ip': u'192.168.1.12',
             u'hypervisor_hostname': u'host2',
             u'hypervisor_type': u'kvm',
             u'hypervisor_version': 1000,
             u'id': u'2',
             u'local_gb': 300000,
             u'memory_mb': 400000,
             u'service': {u'disabled_reason': None,
                          u'host': u'host2',
                          u'id': 8},
             u'state': u'up',
             u'status': u'enabled',
             u'vcpus': 500}]

        def process(hit):
            hit.pop('updated_at')
            return hit

        actual_sources = [process(hit['_source']) for hit in hits]
        self.assertEqual(expected_sources, actual_sources)
