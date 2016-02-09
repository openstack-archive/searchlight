# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
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

import datetime
import mock
from oslo_utils import timeutils

from searchlight.listener import NotificationEndpoint
from searchlight.tests import functional
from searchlight.tests.functional import test_api
from searchlight.tests.functional import test_listener


# This is in the load file
TENANT1 = "8eaac046b2c44ab99246cb0850c7f06d"
TENANT2 = "aaaaaabbbbbbccccc555552222255511"
_now_str = timeutils.isotime(datetime.datetime.utcnow())


class TestNeutronPlugins(functional.FunctionalTest):
    def setUp(self):
        super(TestNeutronPlugins, self).setUp()
        self.networks_plugin = self.initialized_plugins['OS::Neutron::Net']
        self.network_objects = self._load_fixture_data('load/networks.json')

    @mock.patch('searchlight.elasticsearch.plugins.utils.get_now_str')
    def test_network_rbac_tenant(self, mock_utcnow_str):
        mock_utcnow_str.return_value = _now_str

        serialized_networks = [self.networks_plugin.serialize(net)
                               for net in self.network_objects]
        self._index(self.networks_plugin.alias_name_listener,
                    self.networks_plugin.get_document_type(),
                    serialized_networks,
                    TENANT2,
                    role_separation=True)

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      TENANT2)
        self.assertEqual(200, response.status)
        self.assertEqual(2, json_content['hits']['total'])

        hits = json_content['hits']['hits']
        expected_names = ['test-shared', 'test-external-router']
        actual_names = [hit['_source']['name'] for hit in hits]

        self.assertEqual(set(expected_names), set(actual_names))

        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "all_projects": True},
            TENANT2, role="admin")
        self.assertEqual(200, response.status)
        self.assertEqual(3, json_content['hits']['total'])

    @mock.patch('searchlight.elasticsearch.plugins.utils.get_now_str')
    def test_network_rbac_shared_external(self, mock_utcnow_str):
        """TENANT2 networks should be visible because they're marked
        shared or router:external
        """
        mock_utcnow_str.return_value = _now_str

        serialized_networks = [self.networks_plugin.serialize(net)
                               for net in self.network_objects]
        self._index(self.networks_plugin.alias_name_listener,
                    self.networks_plugin.get_document_type(),
                    serialized_networks,
                    TENANT2,
                    role_separation=True)

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      TENANT1)

        self.assertEqual(200, response.status)
        self.assertEqual(3, json_content['hits']['total'])

        hits = json_content['hits']['hits']
        expected_names = ['test', 'test-shared', 'test-external-router']
        actual_names = [hit['_source']['name'] for hit in hits]

        self.assertEqual(set(expected_names), set(actual_names))


class TestNeutronListener(test_listener.TestSearchListenerBase):
    def __init__(self, *args, **kwargs):
        super(TestNeutronListener, self).__init__(*args, **kwargs)
        self.network_events = self._load_fixture_data('events/networks.json')
        self.port_events = self._load_fixture_data('events/ports.json')

    def setUp(self):
        super(TestNeutronListener, self).setUp()

        self.networks_plugin = self.initialized_plugins['OS::Neutron::Net']
        self.ports_plugin = self.initialized_plugins['OS::Neutron::Port']

        notification_plugins = {
            plugin.document_type: test_listener.StevedoreMock(plugin)
            for plugin in (self.networks_plugin, self.ports_plugin)}
        self.notification_endpoint = NotificationEndpoint(notification_plugins)

        self.index_name = self.networks_plugin.alias_name_listener

    def test_network_create_event(self):
        '''Send network.create.end notification event to listener'''
        create_event = self.network_events['network.create.end']
        self._send_event_to_listener(create_event, self.index_name)
        result = self._verify_event_processing(create_event, owner=TENANT1)
        verification_keys = ['id', 'status', 'port_security_enabled']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='network')

    def test_network_delete_event(self):
        delete_event = self.network_events['network.delete.end']
        self._send_event_to_listener(delete_event, self.index_name)
        self._verify_event_processing(delete_event, count=0,
                                      owner=TENANT1)

    def test_port_create_event(self):
        create_event = self.port_events['port.create.end']
        self._send_event_to_listener(create_event, self.index_name)
        result = self._verify_event_processing(create_event, owner=TENANT1)
        verification_keys = ['id', 'status', 'mac_address', 'status']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='port')

    def test_port_rename_event(self):
        update_event = self.port_events['port_rename']
        self._send_event_to_listener(update_event, self.index_name)
        result = self._verify_event_processing(update_event, owner=TENANT1)
        verification_keys = ['name']
        self._verify_result(update_event, verification_keys, result,
                            inner_key='port')

    def test_port_attach_detach_events(self):
        create_event = self.port_events['port.create.end']
        self._send_event_to_listener(create_event, self.index_name)
        result = self._verify_event_processing(create_event, owner=TENANT1)
        verification_keys = ['device_owner', 'device_id']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='port')

        attach_event = self.port_events['port_attach']
        self._send_event_to_listener(attach_event, self.index_name)
        result = self._verify_event_processing(attach_event, owner=TENANT1)
        verification_keys = ['device_owner', 'device_id']
        self._verify_result(attach_event, verification_keys, result,
                            inner_key='port')

        detach_event = self.port_events['port_detach']
        self._send_event_to_listener(detach_event, self.index_name)
        result = self._verify_event_processing(attach_event, owner=TENANT1)
        verification_keys = ['device_owner', 'device_id']
        self._verify_result(detach_event, verification_keys, result,
                            inner_key='port')

    def test_port_delete_event(self):
        delete_event = self.port_events['port.delete.end']
        self._send_event_to_listener(delete_event, self.index_name)
        self._verify_event_processing(None, count=0,
                                      owner=TENANT1)
