#    Copyright (c) 2016 Huawei Technology Ltd.
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

import novaclient.v2.server_groups as novaclient_server_groups

from searchlight.elasticsearch.plugins.nova import\
    servergroups as servergroups_plugin
import searchlight.tests.utils as test_utils

SG_ID = "99eedec2-68e7-494c-81b6-2a096cce0df9"
USER_ID = "43db6c7e51754c0d8c8b87278144f789"
PROJECT_ID = "405a8b8100ae47ffaa89730681ee400f"
SG_NAME = "test_group"
MEMBERS = []
POLICIES = ["affinity"]


_now = datetime.datetime.utcnow()
updated_now = _now.strftime('%Y-%m-%dT%H:%M:%SZ')

fake_version_list = [test_utils.FakeVersion('2.1'),
                     test_utils.FakeVersion('2.1')]

nova_version_getter = 'novaclient.v2.client.versions.VersionManager.list'


def _servergroup_fixture(servergroup_id, user_id, project_id, name, members,
                         policies):
    attrs = {
        "user_id": user_id,
        "policies": policies,
        "name": name,
        "members": members,
        "project_id": project_id,
        "id": servergroup_id,
        "metadata": {}
    }

    servergroup = mock.Mock(spec=novaclient_server_groups.ServerGroup, **attrs)
    servergroup.to_dict.return_value = attrs
    return servergroup


class TestServerGroupLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestServerGroupLoaderPlugin, self).setUp()
        self.plugin = servergroups_plugin.ServerGroupIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.servergroup1 = _servergroup_fixture(SG_ID, USER_ID, PROJECT_ID,
                                                 SG_NAME, MEMBERS, POLICIES)

    def test_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Nova::ServerGroup',
                         self.plugin.get_document_type())

    @mock.patch(nova_version_getter, return_value=fake_version_list)
    def test_serialize(self, mock_version):
        expected = {
            "user_id": "43db6c7e51754c0d8c8b87278144f789",
            "policies": ["affinity"],
            "name": "test_group",
            "members": [],
            "project_id": "405a8b8100ae47ffaa89730681ee400f",
            "id": "99eedec2-68e7-494c-81b6-2a096cce0df9",
            "metadata": {},
            'updated_at': updated_now,
        }
        with mock.patch('searchlight.elasticsearch.plugins.utils.get_now_str',
                        return_value=updated_now):
            serialized = self.plugin.serialize(self.servergroup1)
        self.assertEqual(expected, serialized)

    def test_notification_events(self):
        handler = self.plugin.get_notification_handler()
        self.assertEqual(
            set(['servergroup.delete',
                 'servergroup.create',
                 'servergroup.addmember',
                 'compute.instance.delete.end']),
            set(handler.get_event_handlers().keys())
        )
