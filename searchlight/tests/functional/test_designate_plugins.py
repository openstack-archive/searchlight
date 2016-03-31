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

from searchlight.listener import NotificationEndpoint
from searchlight.tests.functional import test_listener


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
            plugin.document_type: test_listener.StevedoreMock(plugin)
            for plugin in (self.zones_plugin, self.recordsets_plugin)}
        self.notification_endpoint = NotificationEndpoint(notification_plugins)

        self.listener_alias = self.zones_plugin.alias_name_listener

    def _create_zone(self):
        create_event = self.zone_events["dns.zone.create"]
        self._send_event_to_listener(create_event, self.listener_alias)
        return create_event, self._verify_event_processing(
            create_event,
            owner=create_event['payload']['tenant_id'])

    def test_zone_create_event(self):
        """Send dns.zone.create notification event to listener"""
        create_event, result = self._create_zone()
        verification_keys = ['id', 'name']
        self._verify_result(create_event, verification_keys, result)

    def test_zone_update_event(self):
        """Send dns.zone.update notification event to listener"""

        # Create a zone
        create_event, result = self._create_zone()

        # Update zone
        update_event = self.zone_events['dns.zone.update']
        self._send_event_to_listener(update_event, self.listener_alias)
        result = self._verify_event_processing(
            update_event,
            owner=update_event['payload']['tenant_id'])
        verification_keys = ['ttl']
        self._verify_result(update_event, verification_keys, result)

    def test_zone_delete_event(self):
        """Send dns.zone.delete notification event to listener"""

        # Create Zone
        create_event, result = self._create_zone()

        # Delete Zone
        delete_event = self.zone_events['dns.zone.delete']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(
            delete_event, count=0,
            owner=delete_event['payload']['tenant_id'])
