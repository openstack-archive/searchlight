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
import mock

from searchlight.tests import functional
from searchlight.tests import utils

TENANT1 = u"1816a16093df465dbc609cf638422a05"
TENANT_ID = u"1dd2c5280b4e45fc9d7d08a81228c891"

fake_version_list = [utils.FakeVersion('2.1'),
                     utils.FakeVersion('2.1')]

nova_version_getter = 'novaclient.v2.client.versions.VersionManager.list'


class TestNovaPlugins(functional.FunctionalTest):
    def setUp(self):
        super(TestNovaPlugins, self).setUp()
        self.hyper_plugin = self.initialized_plugins['OS::Nova::Hypervisor']
        self.hyper_objects = self._load_fixture_data('load/hypervisors.json')
        self.server_plugin = self.initialized_plugins['OS::Nova::Server']
        self.server_objects = self._load_fixture_data('load/servers.json')
        self.flavor_plugin = self.initialized_plugins['OS::Nova::Flavor']
        self.flavor_objects = self._load_fixture_data('load/flavors.json')
        self.server_groups_plugin = \
            self.initialized_plugins['OS::Nova::ServerGroup']
        self.server_groups_objects = \
            self._load_fixture_data('load/server_groups.json')

    @mock.patch(nova_version_getter, return_value=fake_version_list)
    def test_hypervisor_rbac(self, mock_version):
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

    @mock.patch(nova_version_getter, return_value=fake_version_list)
    def _index_data(self, mock_version):

        self._index(self.server_plugin,
                    [utils.DictObj(**server) for server in self.server_objects]
                    )

    def test_query(self):
        self._index_data()
        query = {
            "type": ["OS::Nova::Server"],
            "query": {
                "match_all": {}
            }
        }
        response, json_content = self._search_request(query,
                                                      TENANT_ID)
        self.assertEqual(200, response.status)
        self.assertEqual(1, json_content['hits']['total'])

        hits = json_content['hits']['hits']
        host_id = u'41d7069823d74c9ea8debda9a3a02bb00b2f7d53a0accd1f79429407'
        expected_sources = [{
            u'OS-DCF:diskConfig': u'MANUAL',
            u'OS-EXT-AZ:availability_zone': u'nova',
            u'OS-EXT-STS:power_state': 1,
            u'OS-EXT-STS:task_state': None,
            u'OS-EXT-STS:vm_state': u'active',
            u'OS-SRV-USG:launched_at': u'2016-03-08T08:40:22.000000',
            u'OS-SRV-USG:terminated_at': None,
            u'accessIPv4': u'',
            u'accessIPv6': u'',
            u'addresses': {u'private': [{
                           u'OS-EXT-IPS-MAC:mac_addr': u'fa:16:3e:55:7e:0d',
                           u'OS-EXT-IPS:type': u'fixed',
                           u'addr': u'10.0.0.2',
                           u'version': 4}]},
            u'config_drive': u'True',
            u'created': u'2016-03-08T08:39:33Z',
            u'created_at': u'2016-03-08T08:39:33Z',
            u'flavor': {u'id': u'1'},
            u'hostId': host_id,
            u'id': u'2adc3f33-8af9-43ef-8691-3d29f277e49b',
            u'image': {u'id': u'687c1900-a386-47c8-b591-b0083e7ca316'},
            u'key_name': u'testkey',
            u'metadata': {},
            u'name': u'test1',
            u'networks': [{u'OS-EXT-IPS-MAC:mac_addr': u'fa:16:3e:55:7e:0d',
                           u'OS-EXT-IPS:type': u'fixed',
                           u'ipv4_addr': u'10.0.0.2',
                           u'name': u'private',
                           u'version': 4}],
            u'os-extended-volumes:volumes_attached': [],
            u'owner': u'1dd2c5280b4e45fc9d7d08a81228c891',
            u'project_id': u'1dd2c5280b4e45fc9d7d08a81228c891',
            u'security_groups': [{u'name': u'default'}],
            u'status': u'ACTIVE',
            u'tenant_id': u'1dd2c5280b4e45fc9d7d08a81228c891',
            u'updated': u'2016-03-08T08:40:22Z',
            u'user_id': u'7c97202cf58d43a9ab33016fc403f093'}]

        def process(hit):
            hit.pop('updated_at')
            return hit

        actual_sources = [process(hit['_source']) for hit in hits]
        self.assertEqual(expected_sources, actual_sources)

    def test_flavor_rbac(self):
        self._index(self.flavor_plugin,
                    [utils.FlavorDictObj(**flavor)
                     for flavor in self.flavor_objects]
                    )

        query = {
            "type": ["OS::Nova::Flavor"],
            "query": {
                "match_all": {}
            }
        }

        response, json_content = self._search_request(query, TENANT1)
        expected_sources = [{
            u'OS-FLV-DISABLED:disabled': False,
            u'OS-FLV-EXT-DATA:ephemeral': 0,
            u'disk': 1,
            u"tenant_id": u"",
            u'extra_specs': {},
            u'id': u'1',
            u'name': u'm1.tiny',
            u'os-flavor-access:is_public': True,
            u'ram': 512,
            u'rxtx_factor': 1.0,
            u'swap': u'',
            u'vcpus': 1}]
        hits = json_content['hits']['hits']
        for hit in hits:
            source = hit["_source"]
            source.pop("updated_at")
        actual_sources = [hit["_source"] for hit in hits]
        self.assertEqual(expected_sources, actual_sources)
        self.assertEqual(200, response.status)
        self.assertEqual(1, json_content['hits']['total'])


def test_server_groups_rbac(self):
    self._index(self.server_groups_plugin,
                [utils.DictObj(**server_group) for server_group in
                 self.server_groups_objects])

    query = {
        "type": ["OS::Nova::ServerGroup"],
        "query": {
            "match_all": {}
        }
    }

    response, json_content = self._search_request(query, TENANT1)
    expected_sources = [{
        u"user_id": u"944ff1aa607744ab9400acbf6be7f38a",
        u"policies": [u"affinity"],
        u"name": u"server_group_1",
        u"members": [u"8bf01fe7-1369-4059-92de-95ba11ff21dd"],
        u"project_id": u"d782f6257f0b484c97e9474b74db34a1",
        u"id": u"d0d017d6-0d41-4b32-b9f8-c43f039defc5",
        u"metadata": {}
    }]
    hits = json_content['hits']['hits']
    for hit in hits:
        source = hit["_source"]
        source.pop("updated_at")
    actual_sources = [hit["_source"] for hit in hits]
    self.assertEqual(expected_sources, actual_sources)
    self.assertEqual(200, response.status)
    self.assertEqual(1, json_content['hits']['total'])
