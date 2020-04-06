# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
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

import datetime
from oslo_utils import uuidutils
from unittest import mock

from searchlight.common import utils
from searchlight.elasticsearch.plugins.neutron import\
    ports as port_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'
ID1 = u'813dd936-663e-4e5b-877c-986021b73e2c'
TENANT1 = u'8eaac046b2c44ab99246cb0850c7f06d'
NETWORK1 = u'bc0adf22-3aef-4e7b-8b99-12670b5a76b5'
UUID_PORT_ID = uuidutils.generate_uuid()
_now_str = utils.isotime(datetime.datetime.utcnow())


def _create_port_fixture(port_id, tenant_id, network_id, **kwargs):
    port = {
        u'admin_state_up': True,
        u'allowed_address_pairs': [],
        u'binding:host_id': u'devstack',
        u'binding:profile': {},
        u'binding:vif_details': {u'ovs_hybrid_plug': True,
                                 u'port_filter': True},
        u'binding:vif_type': u'ovs',
        u'binding:vnic_type': u'normal',
        u'device_id': None,
        u'device_owner': 'compute:None',
        u'dns_assignment': [{
            u'fqdn': u'host-fd70-b64a-666f--1.openstacklocal.',
            u'hostname': u'host-fd70-b64a-666f--1',
            u'ip_address': u'fd70:b64a:666f::1'
        }],
        u'dns_name': u'',
        u'extra_dhcp_opts': [],
        u'fixed_ips': [{
            u'ip_address': u'fd70:b64a:666f::1',
            u'subnet_id': u'356bbedc-2bb2-467a-b380-8bfd0ed2fbdf'
        }],
        u'id': port_id,
        u'mac_address': u'fa:16:3e:19:c8:f5',
        u'name': u'',
        u'network_id': network_id,
        u'port_security_enabled': True,
        u'security_groups': [],
        u'status': u'ACTIVE',
        u'tenant_id': tenant_id,
        u'updated_at': _now_str,
        u'created_at': _now_str
    }
    port.update(**kwargs)
    return port


class TestPortLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestPortLoaderPlugin, self).setUp()
        self.plugin = port_plugin.PortIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.port = _create_port_fixture(ID1, TENANT1, NETWORK1)
        self.none_port = _create_port_fixture(UUID_PORT_ID, TENANT1, NETWORK1,
                                              device_owner=None)
        self.dhcp_port = _create_port_fixture(UUID_PORT_ID, TENANT1, NETWORK1,
                                              device_owner='network:dhcp')
        # device_owner is 'compute:*', indexed.
        self.indexed_ports = [self.port]
        # device_owner is not 'compute:*', not indexed.
        self.ignored_ports = [self.dhcp_port, self.none_port]

    def test_default_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Neutron::Port',
                         self.plugin.get_document_type())

    def test_rbac_filter_admin_role(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=True
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)
        expected_rbac = [
            {'term': {'tenant_id': TENANT1}},
            {
                'has_parent': {
                    'type': self.plugin.parent_plugin_type(),
                    'query': {
                        "bool": {
                            "should": [
                                {'term': {'shared': True}},
                                {'term': {'router:external': True}}
                            ]
                        }
                    }
                }
            }
        ]
        self.assertEqual(expected_rbac, rbac_terms)

    def test_rbac_filter_non_admin_role(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)
        self.assertEqual(
            [{"term": {"tenant_id": TENANT1}}],
            rbac_terms
        )

    def test_admin_only_fields(self):
        admin_only_fields = self.plugin.admin_only_fields
        self.assertEqual(['binding:*'], admin_only_fields)

    def test_indexed_ports(self):
        with mock.patch('neutronclient.v2_0.client.Client.list_ports',
                        return_value={'ports': self.indexed_ports}):
            listed_objects = list(self.plugin.get_objects())
            self.assertEqual([self.port], listed_objects)

    def test_ignored_ports(self):
        with mock.patch('neutronclient.v2_0.client.Client.list_ports',
                        return_value={'ports': self.ignored_ports}):
            listed_objects = list(self.plugin.get_objects())
            self.assertEqual([], listed_objects)

    def test_serialize(self):
        serialized = self.plugin.serialize(self.port)
        # project id should get copied from tenant_id
        self.assertEqual(TENANT1, serialized['project_id'])
