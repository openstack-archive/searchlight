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

from searchlight.common import resource_types
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.neutron import notification_handlers
from searchlight.elasticsearch.plugins.neutron import serialize_port
from searchlight.elasticsearch.plugins import openstack_clients


class PortIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.PortHandler

    ADMIN_ONLY_FIELDS = ["binding:*"]

    @classmethod
    def get_document_type(cls):
        return resource_types.NEUTRON_PORT

    @classmethod
    def parent_plugin_type(cls):
        return 'OS::Neutron::Net'

    def get_parent_id_field(self):
        return 'network_id'

    def get_mapping(self):
        string_not_analyzed = {'type': 'string', 'index': 'not_analyzed'}
        ordered_string = {'type': 'string',
                          'fields': {'raw': string_not_analyzed}}

        # TODO(sjmc7): denormalize 'device' fields (instance_id, router_id)?
        return {
            'dynamic': False,
            'properties': {
                'admin_state_up': {'type': 'boolean'},
                'binding:host_id': string_not_analyzed,
                'binding:vif_details': {'type': 'object', 'properties': {}},
                'binding:vif_type': string_not_analyzed,
                'binding:profile': {'type': 'object', 'properties': {}},
                'binding:vnic_type': string_not_analyzed,
                'created_at': {'type': 'date'},
                # device_owner and device_id identifies e.g which router
                # or instance 'owns' a port
                'device_id': string_not_analyzed,
                'device_owner': string_not_analyzed,
                'dns_name': string_not_analyzed,
                'extra_dhcp_opts': {
                    'type': 'nested',
                    'properties': {
                        'opt_name': string_not_analyzed,
                        'opt_value': string_not_analyzed
                    }
                },
                'fixed_ips': {
                    'type': 'nested',
                    'properties': {
                        'subnet_id': string_not_analyzed,
                        'ip_address': string_not_analyzed
                    }
                },
                'id': string_not_analyzed,
                'mac_address': string_not_analyzed,
                'name': ordered_string,
                'network_id': string_not_analyzed,
                'port_security_enabled': {'type': 'boolean'},
                'project_id': string_not_analyzed,
                'tenant_id': string_not_analyzed,
                'security_groups': string_not_analyzed,
                'status': string_not_analyzed,
                'updated_at': {'type': 'date'}
            },
            "_meta": {
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "fixed_ips.subnet_id": {
                    "resource_type": resource_types.NEUTRON_SUBNET
                }
            }
        }

    @property
    def admin_only_fields(self):
        from_conf = super(PortIndex, self).admin_only_fields
        return from_conf + PortIndex.ADMIN_ONLY_FIELDS

    @property
    def facets_with_options(self):
        return ('binding:vif_type', 'device_owner', 'admin_state_up', 'status',
                'binding:vnic_type', 'port_security_enabled')

    @property
    def facets_excluded(self):
        return {'tenant_id': True, 'project_id': True}

    @property
    def resource_allowed_policy_target(self):
        # Neutron only supports policy for individual resources
        return None

    @property
    def service_type(self):
        return 'network'

    def _get_rbac_field_filters(self, request_context):
        if request_context.is_admin:
            '''lakshmiS: neutron allows users with admin role to
            see ports of network(s) from other tenants when those
            networks are either shared or external.'''
            has_parent = {
                'has_parent': {
                    'type': self.parent_plugin_type(),
                    'query': {
                        "bool": {
                            "should": [
                                {'term': {'shared': True}},
                                {'term': {'router:external': True}}
                            ]
                        }
                    }
                }
            }

            return [
                {'term': {'tenant_id': request_context.owner}},
                has_parent  # from above
            ]
        else:
            ''' Users without admin role are not allowed to see the
            port information for networks from other tenants even if
            that network was shared or external.'''
            return [
                {'term': {'tenant_id': request_context.owner}}
            ]

    def get_objects(self):
        # This list of owners shamelessly taken from the Neutron code:
        #     neutron/neutron/notifiers/nova.py
        valid_owners = ('compute:', 'baremetal:')

        neutron_client = openstack_clients.get_neutronclient()
        for port in neutron_client.list_ports()['ports']:
            if (not port['device_owner'] or
               not port['device_owner'].startswith(valid_owners)):
                continue
            """The check/TODO below is superseded by the above check. When we
               flesh out the device owner check, re-enable the check below.
            # TODO(sjmc7): Remove this once we can get proper notifications
            # about DHCP ports.
            #  See https://bugs.launchpad.net/searchlight/+bug/1558790
            if port['device_owner'] == 'network:dhcp':
                continue
            """

            yield port

    def serialize(self, port):
        return serialize_port(port)
