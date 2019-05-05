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
from searchlight.elasticsearch.plugins.neutron import serialize_subnet
from searchlight.elasticsearch.plugins import openstack_clients


class SubnetIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.SubnetHandler

    @classmethod
    def get_document_type(cls):
        return resource_types.NEUTRON_SUBNET

    @classmethod
    def parent_plugin_type(cls):
        return 'OS::Neutron::Net'

    def get_parent_id_field(self):
        return 'network_id'

    def get_mapping(self):
        return {
            'dynamic': False,
            'properties': {
                'allocation_pools': {
                    'type': 'nested',
                    'properties': {
                        'start': {'type': 'string', 'index': 'not_analyzed'},
                        'end': {'type': 'string', 'index': 'not_analyzed'},
                    }
                },
                'cidr': {'type': 'string', 'index': 'not_analyzed'},
                'created_at': {'type': 'date'},
                'description': {'type': 'string'},
                'dns_nameservers': {'type': 'string', 'index': 'not_analyzed'},
                'enable_dhcp': {'type': 'boolean'},
                'gateway_ip': {'type': 'string', 'index': 'not_analyzed'},
                'host_routes': {
                    'type': 'nested',
                    'properties': {
                        'destination': {'type': 'string',
                                        'index': 'not_analyzed'},
                        'next_hop': {'type': 'string',
                                     'index': 'not_analyzed'}
                    }
                },
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'ip_version': {'type': 'short'},
                'ipv6_address_mode': {'type': 'string',
                                      'index': 'not_analyzed'},
                'ipv6_ra_mode': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'network_id': {'type': 'string', 'index': 'not_analyzed'},
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'subnetpool_id': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string', 'index': 'not_analyzed'},
                'updated_at': {'type': 'date'}
            },
            "_meta": {
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "subnetpool_id": {
                    "resource_type": resource_types.NEUTRON_SUBNET_POOL
                }
            }
        }

    @property
    def requires_role_separation(self):
        return self.parent_plugin.requires_role_separation

    @property
    def facets_with_options(self):
        return ('ip_version', 'dns_nameservers', 'network_id', 'enable_dhcp',
                'ipv6_address_mode', 'ipv6_ra_mode')

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
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
            see subnet(s) of network(s) from other tenants when those
            networks are either shared or external.'''
            has_parent_query = {
                "bool": {
                    "should": [
                        {'term': {'shared': True}},
                        {'term': {'router:external': True}}
                    ]
                }
            }
        else:
            """Subnet(s) are visible to their owners or if they belong
            to networks with the 'shared' property for users without admin
            role.
            """
            has_parent_query = {'term': {'shared': True}}

        rbac_filter = [
            {'term': {'tenant_id': request_context.owner}},
            {
                'has_parent': {
                    'type': self.parent_plugin_type(),
                    'query': has_parent_query
                }
            }
        ]
        return rbac_filter

    def get_objects(self):
        neutron_client = openstack_clients.get_neutronclient()
        for subnet in neutron_client.list_subnets()['subnets']:
            yield subnet

    def serialize(self, subnet):
        return serialize_subnet(subnet)
