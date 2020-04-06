# Copyright (c) 2015-2016 Hewlett-Packard Development Company, L.P.
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

from unittest import mock

from searchlight.listener import NotificationEndpoint
from searchlight.pipeline import PipelineManager
from searchlight.tests import functional
from searchlight.tests.functional import test_listener
from searchlight.tests import utils


PROJECT1 = "34518c16d95e40a19b1a95c1916d8335"
PROJECT2 = "78d384ce822d420084d706a167f84c95"

EVENT_TENANT1 = "80264096ac454d3d904002491fafe2ec"
EVENT_RS_ID = "cfe39618-49da-4877-914b-f25ef0fb3dc1"
EVENT_ZONE_ID = "3081593e-10ca-408c-af77-1397e689c177"


class TestDesignatePlugins(functional.FunctionalTest):
    def setUp(self):
        super(TestDesignatePlugins, self).setUp()
        self.zone_plugin = self.initialized_plugins['OS::Designate::Zone']
        self.rs_plugin = self.initialized_plugins['OS::Designate::RecordSet']
        self.zone_objects = self._load_fixture_data('load/zones.json')
        self.rs_objects = self._load_fixture_data('load/recordsets.json')

    def test_zone_rbac(self):
        self._index(self.zone_plugin, self.zone_objects)
        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Designate::Zone"},
            PROJECT1)

        self.assertEqual(1, len(json_content['hits']['hits']))
        # Shouldn't see the admin-example zone belonging to project2
        self.assertEqual('example.com.',
                         json_content['hits']['hits'][0]['_source']['name'])

    def test_recordset_rbac(self):
        self._index(self.rs_plugin, self.rs_objects)
        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Designate::RecordSet"},
            PROJECT1)
        self.assertEqual(2, len(json_content['hits']['hits']))

        hit_zone_names = set(h['_source']['zone_name']
                             for h in json_content['hits']['hits'])
        # Shouldn't see any admin-example results
        self.assertEqual(set(['example.com.']), hit_zone_names)


class TestDesignateListener(test_listener.TestSearchListenerBase):
    def __init__(self, *args, **kwargs):
        super(TestDesignateListener, self).__init__(*args, **kwargs)
        self.zone_events = self._load_fixture_data('events/zones.json')
        self.recordset_events = self._load_fixture_data(
            'events/recordsets.json')
        self.record_events = self._load_fixture_data('events/records.json')

    def setUp(self):
        super(TestDesignateListener, self).setUp()

        self.zones_plugin = self.initialized_plugins['OS::Designate::Zone']
        self.recordsets_plugin = self.initialized_plugins[
            'OS::Designate::RecordSet']

        '''openstack_client_mod = "searchlight.elasticsearch.plugins." \
                               "openstack_clients.get_designateclient"
        osclient_patcher = mock.patch(
            openstack_client_mod,
            mock_designate_pyclient.get_fake_designate_client
        )
        osclient_patcher.start()
        self.addCleanup(osclient_patcher.stop)'''

        notification_plugins = {
            plugin.document_type: utils.StevedoreMock(plugin)
            for plugin in (self.zones_plugin, self.recordsets_plugin)}
        self.notification_endpoint = NotificationEndpoint(
            notification_plugins,
            PipelineManager(notification_plugins)
        )

        self.listener_alias = self.zones_plugin.alias_name_listener

    @mock.patch('searchlight.elasticsearch.plugins.designate._get_recordsets')
    def test_zone_cud_events(self, mock_get_recordsets):
        """Test CUD operations for zones"""
        mock_get_recordsets.return_value = []

        create_event = self.zone_events["dns.zone.create"]
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(
            create_event)
        verification_keys = ['id', 'name']
        self._verify_result(create_event, verification_keys, result)

        mock_get_recordsets.assert_called_with(EVENT_ZONE_ID)

        # Update zone
        update_event = self.zone_events['dns.zone.update']
        self._send_event_to_listener(update_event, self.listener_alias)
        result = self._verify_event_processing(
            update_event)
        verification_keys = ['ttl']
        self._verify_result(update_event, verification_keys, result)

        # Delete Zone
        delete_event = self.zone_events['dns.zone.delete']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(
            delete_event, count=0)

    @mock.patch('searchlight.elasticsearch.plugins.designate._get_recordsets')
    def test_zone_create_recordsets(self, mock_get_recordsets):
        """When a zone's created, the event processing requests recordsets
        created as part of the process.
        """
        recordset_objects = self._load_fixture_data('load/recordsets.json')

        create_event = self.zone_events["dns.zone-recordset.create"]
        zone_id = create_event['payload']['id']

        # Simulate what would come back from the recordset API call
        zone_records = list(filter(
            lambda r: r['zone_id'] == zone_id,
            recordset_objects))
        self.assertEqual(2, len(zone_records))
        mock_get_recordsets.return_value = zone_records

        self._send_event_to_listener(create_event, self.listener_alias)
        mock_get_recordsets.assert_called_with(zone_id)

        # Expect 3 results; the zone and the recordsets
        self._verify_event_processing(create_event, count=3)

        query = {"filter": {"term": {"zone_id": zone_id}},
                 "type": self.recordsets_plugin.get_document_type()}
        response, search_results = self._search_request(query, EVENT_TENANT1)
        self.assertEqual(2, search_results['hits']['total'])

    def test_recordset_cud_events(self):
        create_event = self.recordset_events["dns.recordset.create"]
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(
            create_event)
        verification_keys = ['id', 'name', 'zone_id', 'type']
        self._verify_result(create_event, verification_keys, result)

        query = {"filter": {"term": {"records": "10.0.0.1"}},
                 "type": self.recordsets_plugin.get_document_type()}
        response, search_results = self._search_request(query, EVENT_TENANT1)
        self.assertEqual(1, search_results['hits']['total'])
        self.assertEqual(EVENT_RS_ID,
                         search_results['hits']['hits'][0]['_source']['id'])

        query['filter']['term']['records'] = "10.0.0.2"
        response, search_results = self._search_request(query, EVENT_TENANT1)
        self.assertEqual(1, search_results['hits']['total'])
        self.assertEqual(EVENT_RS_ID,
                         search_results['hits']['hits'][0]['_source']['id'])

        # Update zone
        update_event = self.recordset_events['dns.recordset.update']
        self._send_event_to_listener(update_event, self.listener_alias)
        result = self._verify_event_processing(
            update_event)
        verification_keys = ['version']
        self._verify_result(update_event, verification_keys, result)

        delete_event = self.recordset_events['dns.recordset.delete']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(
            delete_event, count=0)
