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

from unittest import mock

from ironicclient import exceptions as ironic_exc
from keystoneclient import exceptions as keystone_exc
import searchlight.elasticsearch.plugins.ironic as ironic_plugin
from searchlight.elasticsearch.plugins.ironic import nodes as nodes_plugin
from searchlight.elasticsearch.plugins.ironic import resources as ir_resources
from searchlight.elasticsearch.plugins import openstack_clients
import searchlight.tests.utils as test_utils

NODE_UUID = "1be26c0b-03f2-4d2e-ae87-c02d7f33c123"
NODE_PROPERTIES = {"memory_mb": 4096, "cpu_arch": "x86_64", "local_gb": 10,
                   "cpus": 8},


def _create_node_fixture():
    node = {
        "chassis_uuid": "db0eef9d-45b2-4dc0-94a8-fc283c01171f",
        "clean_step": None,
        "console_enabled": False,
        "created_at": "2016-01-26T20:41:03+00:00",
        "driver": "fake",
        "driver_info": {
            "host": "192.168.0.111"},
        "extra": {},
        "inspection_finished_at": None,
        "inspection_started_at": None,
        "instance_info": {},
        "instance_uuid": None,
        "last_error": None,
        "maintenance": False,
        "maintenance_reason": None,
        "network_interface": "flat",
        "name": None,
        "power_state": "power off",
        "properties": NODE_PROPERTIES,
        "provision_state": "deploying",
        "provision_updated_at": "2016-01-27T20:41:03+00:00",
        "resource_class": None,
        "target_power_state": None,
        "target_provision_state": "active",
        "updated_at": "2016-01-27T20:41:03+00:00",
        "uuid": NODE_UUID
    }

    return node


class TestNodeLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestNodeLoaderPlugin, self).setUp()
        self.plugin = nodes_plugin.NodeIndex()

    def test_default_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Ironic::Node',
                         self.plugin.get_document_type())

    def test_rbac_filter(self):
        rbac = self.plugin._get_rbac_field_filters({})
        self.assertEqual([], rbac)

    def test_admin_only_fields(self):
        admin_only_fields = self.plugin.admin_only_fields
        self.assertEqual([], admin_only_fields)

    def test_document_id(self):
        self.assertEqual('uuid', self.plugin.get_document_id_field())

    def test_facets_with_options(self):
        expected = ('power_state', 'target_power_state', 'provision_state',
                    'target_provision_state', 'maintenance', 'console_enabled')
        self.assertEqual(expected, self.plugin.facets_with_options)

    def test_serialize(self):
        serialized = ironic_plugin.serialize_resource(_create_node_fixture(),
                                                      ir_resources.NODE_FIELDS)
        # id cloned from uuid
        self.assertEqual(NODE_UUID, serialized['id'])
        # if name is not set it's uuid
        self.assertEqual(NODE_UUID, serialized['name'])
        # properties remapped to node_properties
        self.assertEqual(NODE_PROPERTIES, serialized['node_properties'])
        self.assertNotIn('properties', serialized)

    def test_service_not_present_exception(self):
        with mock.patch.object(openstack_clients, '_get_session'):
            with mock.patch('ironicclient.client.get_client') as ironic_cl:

                ironic_cl.side_effect = ironic_exc.AmbiguousAuthSystem
                self.assertRaises(keystone_exc.EndpointNotFound,
                                  openstack_clients.get_ironicclient)
