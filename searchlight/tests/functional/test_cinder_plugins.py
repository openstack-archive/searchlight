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

from unittest import mock

from searchlight.listener import NotificationEndpoint
from searchlight.pipeline import PipelineManager
from searchlight.tests import functional
from searchlight.tests.functional import test_api
from searchlight.tests.functional import test_listener
from searchlight.tests import utils


SERVER_ID = u"ae81266c-a292-4e48-bf81-a3894bd62f4a"
TENANT_ID1 = u"1816a16093df465dbc609cf638422a05"
TENANT_ID2 = u"75c31cdaa3604b76b7e279de50aec9f0"
USER_ID = u"3f7600957f0a444c98928d79debb72fb"
VOLUME_ID1 = u"f54b1d2f-4514-4688-8da7-4bc66767b6be"
VOLUME_ID2 = u"fe7a158a-7f6d-461f-84df-83d394f7c0f6"
VOLUME_ID3 = u"faaad6fe-9351-4313-bce9-881b476d5751"
SNAP_ID1 = u"6d2643b5-d579-417f-b9b9-969ce94dc134"
SNAP_ID2 = u"56f91625-2fc5-4e4a-8284-4bfd3b3a1914"


volume_manager = 'cinderclient.v2.volumes.VolumeManager'
snapshot_manager = 'cinderclient.v2.volume_snapshots.SnapshotManager'


class TestCinderPlugins(functional.FunctionalTest):
    def setUp(self):
        super(TestCinderPlugins, self).setUp()
        self.volume_plugin = self.initialized_plugins['OS::Cinder::Volume']
        self.snapshot_plugin = self.initialized_plugins['OS::Cinder::Snapshot']

        self.volume_objects = self._load_fixture_data('load/volumes.json')
        self.snapshot_objects = self._load_fixture_data('load/snapshots.json')

    def _index_data(self):
        """Moving this here because failures in setUp result in the API server
        not getting torn down properly.
        """
        def fake_volume_get(volume_id):
            vol = list(filter(lambda v: v["id"] == volume_id,
                       self.volume_objects))[0]
            return utils.DictObj(**vol)

        def fake_snapshot_get(snapshot_id):
            snap = list(filter(lambda v: v["id"] == snapshot_id,
                        self.snapshot_objects))[0]
            return utils.DictObj(**snap)

        self._index(self.snapshot_plugin,
                    [utils.DictObj(**snap) for snap in self.snapshot_objects])

        self._index(self.volume_plugin,
                    [utils.DictObj(**vol) for vol in self.volume_objects])

    def test_query_attachments(self):
        self._index_data()
        query = {
            "type": "OS::Cinder::Volume",
            "query": {
                "nested": {
                    "path": "attachments",
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"attachments.device": "/dev/vdb"}},
                                {"term": {"attachments.server_id": SERVER_ID}}
                            ]
                        }
                    }
                }
            }
        }
        response, json_content = self._search_request(query,
                                                      TENANT_ID1)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])

    def test_snapshots_of_volume(self):
        self._index_data()
        query = {
            "type": "OS::Cinder::Snapshot",
            "query": {
                "has_parent": {
                    "parent_type": "OS::Cinder::Volume",
                    "query": {
                        "term": {"id": "fe7a158a-7f6d-461f-84df-83d394f7c0f6"}
                    }
                }
            }
        }
        response, json_content = self._search_request(query,
                                                      TENANT_ID1)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual(SNAP_ID1,
                         json_content['hits']['hits'][0]['_source']['id'])

    def test_rbac(self):
        self._index_data()
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      TENANT_ID1)
        self.assertEqual(200, response.status_code)
        hits = [hit['_source'] for hit in json_content['hits']['hits']]
        self.assertEqual(set([VOLUME_ID1, VOLUME_ID2, SNAP_ID1]),
                         set(h['id'] for h in hits))


class TestCinderNotifications(test_listener.TestSearchListenerBase):
    """Cinder has to go to the API currently so we can't really test the
    search results from notifications, just that there was an attempt to
    retrieve and store the results
    """
    def setUp(self):
        super(TestCinderNotifications, self).setUp()
        self.volume_plugin = self.initialized_plugins['OS::Cinder::Volume']
        self.snapshot_plugin = self.initialized_plugins['OS::Cinder::Snapshot']

        self.volume_events = self._load_fixture_data('events/volumes.json')
        self.snapshot_events = self._load_fixture_data('events/snapshots.json')

        notification_plugins = {
            plugin.document_type: utils.StevedoreMock(plugin)
            for plugin in (self.volume_plugin, self.snapshot_plugin)}
        self.notification_endpoint = NotificationEndpoint(
            notification_plugins,
            PipelineManager(notification_plugins)
        )

        self.index_alias = self.volume_plugin.alias_name_listener

        volume = {
            'id': VOLUME_ID1,
            'user_id': USER_ID,
            'created_at': '2016-03-07T16:51:09.000000',
            'updated_at': '2016-03-07T16:51:09.000000'
        }
        self.volume_fixture = utils.DictObj(**volume)

    @mock.patch(volume_manager + '.get')
    def test_volume_cud(self, mock_volume_get):
        mock_volume_get.return_value = self.volume_fixture

        vol_create = self.volume_events['volume.create.end']
        self._send_event_to_listener(vol_create, self.index_alias)

        vol_update = self.volume_events['volume.update.end']
        self._send_event_to_listener(vol_update, self.index_alias)

        vol_delete = self.volume_events['volume.delete.end']
        self._send_event_to_listener(vol_delete, self.index_alias)

        mock_volume_get.assert_has_calls([
            mock.call(VOLUME_ID1), mock.call(VOLUME_ID1)
        ])

    @mock.patch(volume_manager + '.get')
    def test_volume_attach(self, mock_volume_get):
        mock_volume_get.return_value = self.volume_fixture

        vol_attach = self.volume_events['volume.attach.end']
        self._send_event_to_listener(vol_attach, self.index_alias)

        vol_detach = self.volume_events['volume.detach.end']
        self._send_event_to_listener(vol_detach, self.index_alias)

        mock_volume_get.assert_has_calls([
            mock.call(VOLUME_ID1), mock.call(VOLUME_ID1)
        ])

    @mock.patch(volume_manager + '.get')
    def test_volume_retype(self, mock_volume_get):
        mock_volume = mock.Mock(id=VOLUME_ID1, user_id=USER_ID,
                                created_at='2016-03-07T16:51:09.000000',
                                updated_at='2016-03-07T16:51:09.000000')
        mock_volume_get.return_value = mock_volume

        vol_retype = self.volume_events['volume.retype']
        self._send_event_to_listener(vol_retype, self.index_alias)

        mock_volume_get.assert_called_with(VOLUME_ID1)

    @mock.patch(snapshot_manager + '.get')
    def test_snapshot_create_delete(self, mock_snapshot_get):
        mock_snap = mock.Mock(id=SNAP_ID2,
                              created_at='2016-03-07T16:51:09.000000',
                              updated_at='2016-03-07T16:51:09.000000')
        mock_snapshot_get.return_value = mock_snap

        snapshot_create = self.snapshot_events['snapshot.create.end']
        self._send_event_to_listener(snapshot_create, self.index_alias)

        snapshot_delete = self.snapshot_events['snapshot.delete.end']
        self._send_event_to_listener(snapshot_delete, self.index_alias)

        mock_snapshot_get.assert_has_calls([mock.call(SNAP_ID2)])
