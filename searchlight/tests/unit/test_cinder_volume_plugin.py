# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
# All Rights Reserved.
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

from oslo_utils import uuidutils

from searchlight.elasticsearch.plugins.cinder import serialize_cinder_volume
from searchlight.elasticsearch.plugins.cinder import volumes as volumes_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


USER1 = u'1111bbbbccccc'
ID1 = u'abc1-2345-6789'
ID2 = u'1bac-5bd3-78fd'
SERVER_ID = uuidutils.generate_uuid()
ATTACH_ID = uuidutils.generate_uuid()
TENANT1 = u'aaabbbccc'


_now = datetime.datetime.utcnow()
_five_minutes_ago = _now - datetime.timedelta(minutes=5)
created_now = _five_minutes_ago.strftime(u'%Y-%m-%dT%H:%M:%S.%s')
updated_now = _now.strftime(u'%Y-%m-%dT%H:%M:%S.%s')


def _volume_fixture(volume_id, tenant_id, **kwargs):
    volume = {
        '_info': {
            u'attachments': [],
            u'availability_zone': u'nova',
            # We don't care about any of this; _info should get deleted
            u'volume_type': u'lvmdriver-1'
        },
        '_loaded': True,
        'attachments': [],
        'availability_zone': u'nova',
        'bootable': u'false',
        'consistencygroup_id': None,
        'created_at': created_now,
        'description': None,
        'encrypted': False,
        'id': volume_id,
        'links': [{u'href': u'dont care'}],
        'manager': "A thing that doesn't serialize",
        'metadata': {},
        'migration_status': None,
        'multiattach': False,
        'name': None,
        'os-vol-host-attr:host': u'devstack@lvmdriver-1#lvmdriver-1',
        'os-vol-mig-status-attr:migstat': None,
        'os-vol-mig-status-attr:name_id': None,
        'os-vol-tenant-attr:tenant_id': tenant_id,
        'os-volume-replication:driver_data': None,
        'os-volume-replication:extended_status': None,
        'replication_status': u'disabled',
        'size': 1,
        'snapshot_id': None,
        'source_volid': None,
        'status': u'available',
        'updated_at': updated_now,
        'user_id': USER1,
        'volume_type': u'lvmdriver-1'
    }
    volume.update(*kwargs)
    return test_utils.DictObj(**volume)


def _attachment_fixture(volume_id, server_id, attachment_id, **kwargs):
    attachment = {
        'server_id': server_id,
        'attachment_id': attachment_id,
        'attached_at': updated_now,
        'host_name': None,
        'volume_id': volume_id,
        'device': u'/dev/vdb',
        'id': volume_id
    }
    attachment.update(**kwargs)
    return attachment


class TestVolumePlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestVolumePlugin, self).setUp()
        self.plugin = volumes_plugin.VolumeIndex()
        self.volume1 = _volume_fixture(ID1, TENANT1)
        self.attached_volume = _volume_fixture(ID2, TENANT1)
        self.attached_volume.attachments.append(
            _attachment_fixture(ID1, SERVER_ID, ATTACH_ID))

    def test_serialize(self):
        with mock.patch('cinderclient.v2.volumes.VolumeManager.get',
                        return_value=self.volume1):
            serialized = serialize_cinder_volume(ID1)
        self.assertNotIn('_info', serialized)
        self.assertNotIn('_loaded', serialized)
        self.assertNotIn('manager', serialized)
        self.assertNotIn('links', serialized)
        self.assertEqual(TENANT1, serialized['project_id'])

    def test_admin_only(self):
        self.assertEqual(set(['os-vol-mig-status-attr:*', 'os-vol-host-attr:*',
                              'migration_status']),
                         set(self.plugin.admin_only_fields))

    def test_rbac_filters(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        self.assertEqual(
            [{"term": {"project_id": TENANT1}}],
            self.plugin._get_rbac_field_filters(fake_request.context))
