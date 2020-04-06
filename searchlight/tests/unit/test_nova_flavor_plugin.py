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

import novaclient.v2.flavors as novaclient_flavors

from searchlight.elasticsearch.plugins.nova import\
    flavors as flavors_plugin
import searchlight.tests.utils as test_utils

_now = datetime.datetime.utcnow()
updated_now = _now.strftime('%Y-%m-%dT%H:%M:%SZ')

fake_version_list = [test_utils.FakeVersion('2.1'),
                     test_utils.FakeVersion('2.1')]

nova_version_getter = 'novaclient.v2.client.versions.VersionManager.list'


def _flavor_fixture(name, id, ram, vcpus, swap, disk, is_public, ephemeral,
                    extra_specs=None):
    attrs = {
        "name": name,
        "id": id,
        "links": [
            {'href': 'http://127.0.0.1:8774/v2.1/flavors/test', 'rel': 'self'},
            {'href': 'http://127.0.0.1:8774/flavors/test', 'rel': 'bookmark'}
        ],
        "ram": ram,
        "disk": disk,
        "vcpus": vcpus,
        "swap": swap,
        "OS-FLV-EXT-DATA:ephemeral": ephemeral,
        "os-flavor-access:is_public": is_public,
        "OS-FLV-DISABLED:disabled": False,
        "rxtx_factor": 1.0,
    }

    flavor = mock.Mock(spec=novaclient_flavors.Flavor, **attrs)
    flavor.to_dict.return_value = attrs
    flavor.get_keys.return_value = extra_specs or {}
    return flavor


class TestFlavorLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestFlavorLoaderPlugin, self).setUp()
        self.plugin = flavors_plugin.FlavorIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.flavor1 = _flavor_fixture("test_flavor",
                                       "100", 512, 1, 0, 10, True, 0,
                                       extra_specs={"key1": "value1"})
        self.versioned_flavor = {
            'disabled': False,
            'root_gb': 10,
            'name': 'test_flavor',
            'ephemeral_gb': 0,
            'memory_mb': 512,
            'vcpus': 1,
            'swap': 0,
            'rxtx_factor': 1.0,
            'is_public': True,
            'flavorid': '100',
            'extra_specs': {'key1': 'value1'},
            'vcpu_weight': 0
        }

    def test_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Nova::Flavor',
                         self.plugin.get_document_type())

    @mock.patch(nova_version_getter, return_value=fake_version_list)
    def test_serialize(self, mock_version):
        expected = {
            'OS-FLV-DISABLED:disabled': False,
            'OS-FLV-EXT-DATA:ephemeral': 0,
            'disk': 10,
            'extra_specs': {'key1': 'value1'},
            'id': '100',
            'name': 'test_flavor',
            'os-flavor-access:is_public': True,
            'ram': 512,
            'rxtx_factor': 1.0,
            'swap': 0,
            'tenant_access': None,
            'updated_at': updated_now,
            'vcpus': 1
        }
        with mock.patch('searchlight.elasticsearch.plugins.utils.get_now_str',
                        return_value=updated_now):
            serialized1 = self.plugin.serialize(self.flavor1)
            serialized2 = self.plugin.serialize(self.versioned_flavor)
        self.assertEqual(expected, serialized1)
        self.assertEqual(expected, serialized2)

    def test_notification_events(self):
        handler = self.plugin.get_notification_handler()
        self.assertEqual(
            set(['flavor.create',
                 'flavor.update',
                 'flavor.delete']),
            set(handler.get_event_handlers().keys())
        )
