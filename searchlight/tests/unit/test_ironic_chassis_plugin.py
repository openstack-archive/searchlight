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
from searchlight.elasticsearch.plugins.ironic import chassis as chassis_plugin
from searchlight.elasticsearch.plugins.ironic import resources as ir_resources
import searchlight.tests.utils as test_utils

CHASSIS_UUID = "1910f669-ce8b-43c2-b1d8-cf3d65be815e"


def _create_chassis_fixture():
    chassis = {
        "created_at": "2016-04-10T10:13:03+00:00",
        "description": "bare 28",
        "extra": {},
        "updated_at": "2016-04-27T21:11:03+00:00",
        "uuid": CHASSIS_UUID
    }

    return chassis


class TestChassisLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestChassisLoaderPlugin, self).setUp()
        self.plugin = chassis_plugin.ChassisIndex()

    def test_default_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Ironic::Chassis',
                         self.plugin.get_document_type())

    def test_rbac_filter(self):
        rbac = self.plugin._get_rbac_field_filters({})
        self.assertEqual([], rbac)

    def test_admin_only_fields(self):
        admin_only_fields = self.plugin.admin_only_fields
        self.assertEqual([], admin_only_fields)

    def test_document_id(self):
        self.assertEqual('uuid', self.plugin.get_document_id_field())

    def test_serialize(self):
        serialized = ironic_plugin.serialize_resource(
            _create_chassis_fixture(), ir_resources.CHASSIS_FIELDS)
        # id cloned from uuid
        self.assertEqual(CHASSIS_UUID, serialized['id'])
        # if name is not set it's uuid
        self.assertEqual(CHASSIS_UUID, serialized['name'])
