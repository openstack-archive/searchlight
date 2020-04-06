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

import copy
from unittest import mock

from oslo_utils import uuidutils

from searchlight.listener import NotificationEndpoint
from searchlight.pipeline import PipelineManager
from searchlight.tests import functional
from searchlight.tests.functional import test_api
from searchlight.tests.functional import test_listener
from searchlight.tests import utils

# These is in the load file
TENANT1 = "8eaac046b2c44ab99246cb0850c7f06d"
TENANT2 = "aaaaaabbbbbbccccc555552222255511"
TENANT3 = "75c31cdaa3604b76b7e279de50aec9f0"
TENANT4 = "1816a16093df465dbc609cf638422a05"

# Event tenant
EV_TENANT = "5fe7c4e4e492490393c674089a178e19"

NETID4 = "60e80dca-302d-4460-8984-9b85dc782bca"

SHARED_NET_ID = "deadbeef-4808-4c88-8c3b-deadbeefdead"


class TestNeutronPlugins(functional.FunctionalTest):
    def setUp(self):
        super(TestNeutronPlugins, self).setUp()
        self.networks_plugin = self.initialized_plugins['OS::Neutron::Net']
        self.subnets_plugin = self.initialized_plugins['OS::Neutron::Subnet']
        self.routers_plugin = self.initialized_plugins['OS::Neutron::Router']
        self.port_plugin = self.initialized_plugins['OS::Neutron::Port']
        self.fip_plugin = self.initialized_plugins['OS::Neutron::FloatingIP']
        self.secgroup_plugin = (
            self.initialized_plugins['OS::Neutron::SecurityGroup'])

        self.network_objects = self._load_fixture_data('load/networks.json')

        self.subnet_objects = self._load_fixture_data('load/subnets.json')
        self.subnet_objects = self.subnet_objects['subnets']

        self.port_objects = self._load_fixture_data('load/ports.json')
        self.port_objects = self.port_objects['ports']

        self.router_objects = self._load_fixture_data('load/routers.json')
        self.router_objects = self.router_objects['routers']

        self.fip_objects = self._load_fixture_data('load/floatingips.json')
        self.fip_objects = self.fip_objects['floatingips']

        self.secgroup_objects = self._load_fixture_data('load/security.json')
        self.secgroup_objects = self.secgroup_objects['securitygroups']

    def test_network_rbac_tenant(self):
        self._index(self.networks_plugin, self.network_objects)

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      TENANT2)
        self.assertEqual(200, response.status_code)
        self.assertEqual(5, json_content['hits']['total'])

        hits = json_content['hits']['hits']
        expected_names = ['test-external-router', 'test-not-shared',
                          'test-shared', 'test1-no-shared-external',
                          'test1-shared-no-external']
        actual_names = [hit['_source']['name'] for hit in hits]

        self.assertEqual(set(expected_names), set(actual_names))

        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "all_projects": True},
            TENANT2, role="admin")
        self.assertEqual(200, response.status_code)
        self.assertEqual(6, json_content['hits']['total'])

    def test_network_rbac_shared_external(self):
        """TENANT2 networks should be visible because they're marked
        shared or router:external
        """
        self._index(self.networks_plugin, self.network_objects)

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      TENANT1)

        self.assertEqual(200, response.status_code)
        self.assertEqual(5, json_content['hits']['total'])

        hits = json_content['hits']['hits']
        expected_names = ['test', 'test-shared', 'test-external-router',
                          'test1-no-shared-external',
                          'test1-shared-no-external']
        actual_names = [hit['_source']['name'] for hit in hits]

        self.assertEqual(set(expected_names), set(actual_names))

    def test_subnet_rbac(self):
        """This test intentionally doesn't set a parent network so that it's
        just testing the tenant id check
        """
        self._index(self.subnets_plugin, self.subnet_objects)

        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Neutron::Subnet"},
            TENANT3)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual(
            "doesnt-exist",
            json_content['hits']['hits'][0]['_source']['network_id'])

    def test_shared_network_subnet(self):
        self._index(self.networks_plugin, self.network_objects)
        self._index(self.subnets_plugin, self.subnet_objects)

        # There are two networks that belong to tenant2; shared-subnet and
        # not-shared-subnet. There's also a subnet called shared-not-external
        # that belongs to network id cf14a7a7-4808-4c88-8c3b-56fb48f2b1d1
        # and which is visible to TENANT2
        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Neutron::Subnet"},
            TENANT2)
        self.assertEqual(3, json_content['hits']['total'])
        self.assertEqual(
            set(['shared-subnet', 'not-shared-subnet', 'shared-not-external']),
            set([h['_source']['name'] for h in json_content['hits']['hits']]))

        # Tenant 3 can see the two shared network's subnets plus the one
        # that belongs to TENANT3
        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Neutron::Subnet"},
            TENANT3)
        self.assertEqual(3, json_content['hits']['total'])
        self.assertEqual(
            set(['shared-subnet', 'shared-not-external',
                 'ipv6-public-subnet']),
            set([h['_source']['name'] for h in json_content['hits']['hits']]))

    def test_subnet_rbac_admin_role_non_tenant(self):
        self._index(self.networks_plugin, self.network_objects)

        # Index all subnets
        self._index(self.subnets_plugin, self.subnet_objects)

        # There are now two subnets from two other tenant networks
        # which are either shared or external along with all subnets
        # from own tenant
        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Neutron::Subnet",
             "all_projects": False}, TENANT1, role="admin")
        self.assertEqual(4, json_content['hits']['total'])

    def test_port_rbac_admin_role_non_tenant(self):
        """Test that a user with admin role can access ports from
        all the tenants where a network is either shared or external.
        """
        self._index(self.networks_plugin, self.network_objects)

        self._index(self.port_plugin, self.port_objects)

        response, json_content = self._search_request(
            {"query": {"match_all": {}}, "type": "OS::Neutron::Port",
             "all_projects": False}, TENANT1, role="admin")
        self.assertEqual(200, response.status_code)
        self.assertEqual(2, json_content['hits']['total'])

    def test_router_rbac(self):
        self._index(self.routers_plugin,
                    self.router_objects)

        query = {"query": {"match_all": {}}, "type": "OS::Neutron::Router"}
        response, json_content = self._search_request(query,
                                                      TENANT3)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual('0b143748-44d2-4545-9230-864c3abbc786',
                         json_content['hits']['hits'][0]['_source']['id'])

        response, json_content = self._search_request(query,
                                                      TENANT4)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual('324d16fc-c381-4ea4-8f77-feda17cea1d7',
                         json_content['hits']['hits'][0]['_source']['id'])

    def test_router_fixed_ip(self):
        self._index(self.routers_plugin,
                    self.router_objects)

        query = {
            "query": {
                "nested": {
                    "path": "external_gateway_info",
                    "query": {
                        "term": {"external_gateway_info.enable_snat": True}
                    }
                }
            },
            "type": "OS::Neutron::Router"
        }
        response, json_content = self._search_request(query,
                                                      TENANT4)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])

        fixed_ip_path = "external_gateway_info.external_fixed_ips"
        ip_addr = "%s.ip_address" % fixed_ip_path
        net_id = "external_gateway_info.network_id"
        query = {
            "query": {
                "nested": {
                    "path": "external_gateway_info",
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {net_id: "fake-router-network-id"}},
                                {"nested": {
                                    "path": fixed_ip_path,
                                    "query": {
                                        "term": {ip_addr: "2001:db8::1"}}
                                }}
                            ]
                        }
                    }
                }
            }
        }
        response, json_content = self._search_request(query,
                                                      TENANT4)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])

    def test_floatingip_rbac_admin(self):
        self._index(self.fip_plugin,
                    self.fip_objects)
        query = {"query": {"match_all": {}}, "type": "OS::Neutron::FloatingIP"}
        response, json_content = self._search_request(query,
                                                      TENANT3)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual('f0ff4710-e6f6-42c3-b6af-1b15f91e84b0',
                         json_content['hits']['hits'][0]['_source']['id'])

        query['all_projects'] = True
        response, json_content = self._search_request(query, TENANT3,
                                                      role='admin')
        self.assertEqual(200, response.status_code)
        self.assertEqual(2, json_content['hits']['total'])

    def test_secgroup_rbac(self):
        self._index(self.secgroup_plugin,
                    self.secgroup_objects)
        query = {"query": {"match_all": {}},
                 "type": "OS::Neutron::SecurityGroup"}
        response, json_content = self._search_request(query, TENANT1)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual('223c7074-e593-43f2-a0e6-f6d87ee8fb36',
                         json_content['hits']['hits'][0]['_source']['id'])

        response, json_content = self._search_request(query, TENANT3)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual('57512cb7-aa80-9129-b8cc-ddc93612760a',
                         json_content['hits']['hits'][0]['_source']['id'])


class TestNeutronListeners(test_listener.TestSearchListenerBase):
    def __init__(self, *args, **kwargs):
        super(TestNeutronListeners, self).__init__(*args, **kwargs)
        self.network_events = self._load_fixture_data('events/networks.json')
        self.port_events = self._load_fixture_data('events/ports.json')
        self.subnet_events = self._load_fixture_data('events/subnets.json')
        self.router_events = self._load_fixture_data('events/routers.json')
        self.fip_events = self._load_fixture_data('events/floatingips.json')
        self.secgroup_events = self._load_fixture_data('events/security.json')

    def setUp(self):
        super(TestNeutronListeners, self).setUp()

        self.networks_plugin = self.initialized_plugins['OS::Neutron::Net']
        self.ports_plugin = self.initialized_plugins['OS::Neutron::Port']
        self.subnets_plugin = self.initialized_plugins['OS::Neutron::Subnet']
        self.routers_plugin = self.initialized_plugins['OS::Neutron::Router']
        self.fip_plugin = self.initialized_plugins['OS::Neutron::FloatingIP']
        self.secgroup_plugin = (
            self.initialized_plugins['OS::Neutron::SecurityGroup'])

        notification_plugins = {
            plugin.document_type: utils.StevedoreMock(plugin)
            for plugin in (self.networks_plugin, self.ports_plugin,
                           self.subnets_plugin, self.routers_plugin,
                           self.fip_plugin, self.secgroup_plugin)}
        self.notification_endpoint = NotificationEndpoint(
            notification_plugins,
            PipelineManager(notification_plugins)
        )

        self.listener_alias = self.networks_plugin.alias_name_listener

    def test_network_create_update_delete(self):
        '''Send network.create.end notification event to listener'''
        create_event = self.network_events['network.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(create_event, owner=EV_TENANT)
        verification_keys = ['id', 'status', 'port_security_enabled', 'name']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='network')

        hit = result['hits']['hits'][0]['_source']
        self.assertEqual('2016-03-21T16:19:51', hit['updated_at'])

        update_event = self.network_events['network.update.end']
        self._send_event_to_listener(update_event, self.listener_alias)
        result = self._verify_event_processing(update_event, owner=EV_TENANT)
        verification_keys = ['id', 'status', 'port_security_enabled', 'name']
        self._verify_result(update_event, verification_keys, result,
                            inner_key='network')

        rbac_create_event = self.network_events['rbac_policy.create.end']
        self._send_event_to_listener(rbac_create_event, self.listener_alias)
        result = self._verify_event_processing(rbac_create_event,
                                               owner=EV_TENANT)
        cbody = result['hits']['hits'][0]['_source']
        # Verify internal states are not visible.
        self.assertNotIn('members', cbody)
        self.assertNotIn('rbac_policy', cbody)

        rbac_delete_event = self.network_events['rbac_policy.delete.end']
        self._send_event_to_listener(rbac_delete_event, self.listener_alias)
        result = self._verify_event_processing(rbac_delete_event,
                                               owner=EV_TENANT)
        dbody = result['hits']['hits'][0]['_source']
        # Verify internal states are not visible.
        self.assertNotIn('members', dbody)
        self.assertNotIn('rbac_policy', dbody)

        delete_event = self.network_events['network.delete.end']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(delete_event, count=0,
                                      owner=EV_TENANT)

    def test_port_create_event(self):
        create_event = self.port_events['port.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(create_event, owner=EV_TENANT)
        verification_keys = ['id', 'status', 'mac_address', 'status']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='port')
        hit = result['hits']['hits'][0]['_source']
        self.assertEqual('2016-03-21T16:36:56', hit['updated_at'])

    def test_port_rename_event(self):
        update_event = self.port_events['port_rename']
        self._send_event_to_listener(update_event, self.listener_alias)
        result = self._verify_event_processing(update_event, owner=EV_TENANT)
        verification_keys = ['name']
        self._verify_result(update_event, verification_keys, result,
                            inner_key='port')

    def test_port_attach_detach_events(self):
        create_event = self.port_events['port.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(create_event, owner=EV_TENANT)
        verification_keys = ['device_owner', 'device_id']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='port')

        attach_event = self.port_events['port_attach']
        self._send_event_to_listener(attach_event, self.listener_alias)
        result = self._verify_event_processing(attach_event, owner=EV_TENANT)
        verification_keys = ['device_owner', 'device_id']
        self._verify_result(attach_event, verification_keys, result,
                            inner_key='port')

        detach_event = self.port_events['port_detach']
        self._send_event_to_listener(detach_event, self.listener_alias)
        result = self._verify_event_processing(attach_event, owner=EV_TENANT)
        verification_keys = ['device_owner', 'device_id']
        self._verify_result(detach_event, verification_keys, result,
                            inner_key='port')

    def test_port_delete_event(self):
        delete_event = self.port_events['port.delete.end']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(None, count=0,
                                      owner=EV_TENANT)

    def test_subnet_create_update_delete(self):
        create_event = self.subnet_events['subnet.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(create_event, owner=EV_TENANT)
        verification_keys = ['network_id', 'name']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='subnet')

        update_event = self.subnet_events['subnet.update.end']
        self._send_event_to_listener(update_event, self.listener_alias)
        result = self._verify_event_processing(update_event, owner=EV_TENANT)
        verification_keys = ['network_id', 'name']
        self._verify_result(update_event, verification_keys, result,
                            inner_key='subnet')

        delete_event = self.subnet_events['subnet.delete.end']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(delete_event, count=0,
                                      owner=EV_TENANT)

    def test_router_create_update_delete(self):
        create_event = self.router_events['router.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(create_event, owner=EV_TENANT)
        verification_keys = ['status', 'name', 'id']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='router')

        update_event = self.router_events['router.update.end']
        self._send_event_to_listener(update_event, self.listener_alias)
        result = self._verify_event_processing(update_event, owner=EV_TENANT)
        verification_keys = ['status', 'name', 'id']
        self._verify_result(update_event, verification_keys, result,
                            inner_key='router')

        delete_event = self.router_events['router.delete.end']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(delete_event, count=0,
                                      owner=EV_TENANT)

    def test_router_interface_create_delete(self):
        """Check that port creation and deletion is registered on interface
        creation and deletion events
        """
        interface_port = {
            u'port': {
                u'admin_state_up': True,
                u'allowed_address_pairs': [],
                u'binding:vnic_type': u'normal',
                u'device_id': u'9262552b-6e46-41ee-9ede-393d5f65f325',
                u'device_owner': u'network:router_interface',
                u'dns_name': None,
                u'extra_dhcp_opts': [],
                u'fixed_ips': [{
                    u'ip_address': u'172.45.1.1',
                    u'subnet_id': u'4cd5c1d7-68ec-4e9a-bf16-9fd7571f8805'
                }],
                u'id': u'a5324522-47d3-4547-85df-a01ef6bde4b1',
                u'mac_address': u'fa:16:3e:5f:06:e3',
                u'name': u'',
                u'network_id': NETID4,
                u'port_security_enabled': False,
                u'security_groups': [],
                u'status': u'ACTIVE',
                u'tenant_id': EV_TENANT,
                u'created_at': '2016-03-17T18:54:23',
                u'updated_at': '2016-03-17T19:58:13'
            }
        }
        create_event = self.router_events['router.interface.create']
        with mock.patch('neutronclient.v2_0.client.Client.show_port',
                        return_value=interface_port):
            self._send_event_to_listener(create_event, self.listener_alias)

        query = {
            "type": "OS::Neutron::Port",
            "query": {"term": {"id": "a5324522-47d3-4547-85df-a01ef6bde4b1"}}
        }
        response, json_content = self._search_request(query,
                                                      EV_TENANT)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        hit = json_content['hits']['hits'][0]['_source']

        self.assertEqual(NETID4, hit['network_id'])
        self.assertEqual('network:router_interface', hit['device_owner'])

        delete_event = self.router_events['router.interface.delete']
        self._send_event_to_listener(delete_event, self.listener_alias)

        response, json_content = self._search_request(query,
                                                      EV_TENANT)
        self.assertEqual(0, json_content['hits']['total'])

    def test_ignore_neutron_dhcp_port(self):
        create_event = self.port_events['port.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)

        dhcp_event = copy.deepcopy(create_event)
        dhcp_event['payload']['port']['id'] = uuidutils.generate_uuid()
        dhcp_event['payload']['port']['device_owner'] = 'network:dhcp'
        self._send_event_to_listener(dhcp_event, self.listener_alias)

        query = {"type": "OS::Neutron::Port", "query": {"match_all": {}}}
        response, json_content = self._search_request(query,
                                                      EV_TENANT)
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual(create_event['payload']['port']['id'],
                         json_content['hits']['hits'][0]['_source']['id'])

    def test_floatingip_cud_events(self):
        create_event = self.fip_events['floatingip.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)
        result = self._verify_event_processing(create_event, owner=EV_TENANT)
        verification_keys = ['status', 'floating_network_id', 'id',
                             'fixed_ip_address', 'port_id']
        self._verify_result(create_event, verification_keys, result,
                            inner_key='floatingip')

        # Now associate it with a port
        associate_event = self.fip_events['floatingip.associate.end']
        self._send_event_to_listener(associate_event, self.listener_alias)
        result = self._verify_event_processing(associate_event,
                                               owner=EV_TENANT)
        verification_keys = ['status', 'floating_network_id', 'id',
                             'fixed_ip_address', 'port_id']
        self._verify_result(associate_event, verification_keys, result,
                            inner_key='floatingip')

        disassociate_event = self.fip_events['floatingip.disassociate.end']
        self._send_event_to_listener(disassociate_event, self.listener_alias)
        result = self._verify_event_processing(disassociate_event,
                                               owner=EV_TENANT)
        verification_keys = ['status', 'floating_network_id', 'id',
                             'fixed_ip_address', 'port_id']
        self._verify_result(disassociate_event, verification_keys, result,
                            inner_key='floatingip')

        delete_event = self.fip_events['floatingip.delete.end']
        self._send_event_to_listener(delete_event, self.listener_alias)
        self._verify_event_processing(delete_event, count=0,
                                      owner=EV_TENANT)

    def test_secgroup_create_delete(self):
        # Test #1: Create a security group.
        create_event = self.secgroup_events['security_group.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)

        query = {"query": {"match_all": {}},
                 "type": "OS::Neutron::SecurityGroup"}
        response, json_content = self._search_request(query, EV_TENANT)

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, json_content['hits']['total'])
        self.assertEqual(create_event['payload']['security_group']['id'],
                         json_content['hits']['hits'][0]['_source']['id'])
        # Verify the security group has two security group rules.
        groups = (
            json_content['hits']['hits'][0]['_source']['security_group_rules'])
        self.assertEqual(2, len(groups))

        # Test #2: Create a new security group rule for security group.
        create_event = self.secgroup_events['security_group_rule.create.end']
        self._send_event_to_listener(create_event, self.listener_alias)

        query = {"query": {"match_all": {}},
                 "type": "OS::Neutron::SecurityGroup"}
        response, json_content = self._search_request(query, EV_TENANT)

        self.assertEqual(200, response.status_code)
        # Verify the new rule was added to the security group.
        groups = (
            json_content['hits']['hits'][0]['_source']['security_group_rules'])
        self.assertEqual(3, len(groups))

        # Test #3: Query security groups rules, using nested queries (Passing).
        rule_id = "c36445af-953d-47e4-85d2-2a6ac8fcba14"
        group_id = "223c7074-e593-43f2-a0e6-f6d87ee8fb36"
        query = {"query": {"nested": {
                 "path": "security_group_rules",
                 "query": {"term": {"security_group_rules.id": rule_id}}}}}
        response, json_content = self._search_request(query, EV_TENANT)
        self.assertEqual(200, response.status_code)

        group = json_content['hits']['hits']
        self.assertEqual(1, len(group))
        self.assertEqual(group_id, group[0]['_source']['id'])

        # Test #4: Query security groups rules, using nested queries (Failing).
        rule_id = "c36445af-953d-47e4-85d2-2a6ac8fcba15"  # Wrong last digit.
        query = {"query": {"nested": {
                 "path": "security_group_rules",
                 "query": {"term": {"security_group_rules.id": rule_id}}}}}
        response, json_content = self._search_request(query, EV_TENANT)
        self.assertEqual(200, response.status_code)

        group = json_content['hits']['hits']
        self.assertEqual(0, len(group))

        # Test #5: Delete the new security group rule from security group.
        create_event = self.secgroup_events['security_group_rule.delete.end']
        self._send_event_to_listener(create_event, self.listener_alias)

        query = {"query": {"match_all": {}},
                 "type": "OS::Neutron::SecurityGroup"}
        response, json_content = self._search_request(query, EV_TENANT)

        self.assertEqual(200, response.status_code)
        # Verify the new rule was deleted from the security group.
        groups = (
            json_content['hits']['hits'][0]['_source']['security_group_rules'])
        self.assertEqual(2, len(groups))

        # Test #6. Delete the security group.
        create_event = self.secgroup_events['security_group.delete.end']
        self._send_event_to_listener(create_event, self.listener_alias)

        query = {"query": {"match_all": {}},
                 "type": "OS::Neutron::SecurityGroup"}
        response, json_content = self._search_request(query, EV_TENANT)

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, json_content['hits']['total'])
