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
import searchlight.elasticsearch.plugins.ironic as ironic_plugin
from searchlight.elasticsearch.plugins.ironic import ports as ports_plugin
from searchlight.elasticsearch.plugins.ironic import resources as ir_resources
import searchlight.tests.utils as test_utils

PORT_UUID = "eaaca217-e7d8-47b4-bb41-3f99f20eed89"


def _create_port_fixture():
    port = {
        "address": "77:66:23:34:11:b7",
        "created_at": "2016-02-11T15:23:03+00:00",
        "node_uuid": "5b236cab-ad4e-4220-b57c-e827e858745a",
        "extra": {},
        "local_link_connection": {},
        "pxe_enabled": True,
        "updated_at": "2016-03-27T20:41:03+00:00",
        "uuid": PORT_UUID
    }

    return port


class TestPortLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestPortLoaderPlugin, self).setUp()
        self.plugin = ports_plugin.PortIndex()

    def test_default_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Ironic::Port',
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
        expected = 'pxe_enabled',
        self.assertEqual(expected, self.plugin.facets_with_options)

    def test_serialize(self):
        serialized = ironic_plugin.serialize_resource(_create_port_fixture(),
                                                      ir_resources.PORT_FIELDS)
        # id cloned from uuid
        self.assertEqual(PORT_UUID, serialized['id'])
        # if name is not set it's uuid
        self.assertEqual(PORT_UUID, serialized['name'])
