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

from searchlight.elasticsearch.plugins.cinder import serialize_cinder_snapshot
from searchlight.elasticsearch.plugins.cinder \
    import snapshots as snapshots_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


USER1 = u'1111bbbbccccc'
ID1 = u'1111-2222-3333'
VOLID1 = u'aaaa-cccc-bbbb'
PROJECT1 = u'aaabbbccc'


_now = datetime.datetime.utcnow()
_five_minutes_ago = _now - datetime.timedelta(minutes=5)
created_now = _five_minutes_ago.strftime(u'%Y-%m-%dT%H:%M:%S.%s')
updated_now = _now.strftime(u'%Y-%m-%dT%H:%M:%S.%s')


def _snapshot_fixture(snapshot_id, volume_id, project_id, **kwargs):
    fixture = {
        '_info': {
            u'created_at': created_now,
            u'description': None,
            # blah blah, don't want any of this
            u'volume_id': u'faaad6fe-9351-4313-bce9-881b476d5751'},
        '_loaded': True,
        'created_at': created_now,
        'description': None,
        'id': snapshot_id,
        'manager': "we don't want this",
        'metadata': {},
        'name': None,
        'os-extended-snapshot-attributes:progress': u'100%',
        'os-extended-snapshot-attributes:project_id': project_id,
        'size': 1,
        'status': u'available',
        'updated_at': updated_now,
        'volume_id': volume_id}

    return test_utils.DictObj(**fixture)


class TestSnapshotPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSnapshotPlugin, self).setUp()
        self.plugin = snapshots_plugin.SnapshotIndex()
        self.snapshot1 = _snapshot_fixture(ID1, VOLID1, PROJECT1, name="snap1")

    def test_document_type(self):
        self.assertEqual('OS::Cinder::Snapshot',
                         self.plugin.get_document_type())

    def test_parent_type(self):
        self.assertEqual('OS::Cinder::Volume',
                         self.plugin.parent_plugin_type())

    def test_rbac_filters(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, PROJECT1, '/v1/search/facets', is_admin=True
        )
        rbac_query_fragment = self.plugin._get_rbac_field_filters(
            fake_request.context)

        self.assertEqual([{"term": {"project_id": PROJECT1}}],
                         rbac_query_fragment)

    def test_serialize(self):
        with mock.patch('cinderclient.v2.volume_snapshots.SnapshotManager.get',
                        return_value=self.snapshot1):
            serialized = serialize_cinder_snapshot(ID1)
        self.assertNotIn('_info', serialized)
        self.assertNotIn('_loaded', serialized)
        self.assertNotIn('manager', serialized)

        self.assertEqual(serialized['tenant_id'], PROJECT1)
        self.assertEqual(serialized['project_id'], PROJECT1)
