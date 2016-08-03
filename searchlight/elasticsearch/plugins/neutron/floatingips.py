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
from searchlight.elasticsearch.plugins.neutron import serialize_floatingip
from searchlight.elasticsearch.plugins import openstack_clients


class FloatingIPIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.FloatingIPHandler

    @classmethod
    def get_document_type(cls):
        return resource_types.NEUTRON_FLOATINGIP

    def get_mapping(self):
        str_not_analyzed = {'type': 'string', 'index': 'not_analyzed'}
        return {
            'dynamic': False,
            'properties': {
                'router_id': str_not_analyzed,
                'status': str_not_analyzed,
                'description': {'type': 'string'},
                'dns_domain': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'dns_name': str_not_analyzed,
                'floating_network_id': str_not_analyzed,
                # Note that we can assume ipv4 since NAT to ipv6 is deemed
                # unnecessary and ipv6->ipv4 internal addresses isn't supported
                'fixed_ip_address': {"type": "ip"},
                'floating_ip_address': {"type": "ip"},
                'tenant_id': str_not_analyzed,
                'project_id': str_not_analyzed,
                'port_id': str_not_analyzed,
                'id': str_not_analyzed
            },
            '_meta': {
                'project_id': {
                    'resource_type': resource_types.KEYSTONE_PROJECT
                },
                'tenant_id': {
                    'resource_type': resource_types.KEYSTONE_PROJECT
                },
                'router_id': {
                    'resource_type': resource_types.NEUTRON_ROUTER
                },
                'floating_network_id': {
                    'resource_type': resource_types.NEUTRON_NETWORK,
                },
                'port_id': {
                    'resource_type': resource_types.NEUTRON_PORT,
                }
            }
        }

    @property
    def facets_with_options(self):
        return 'status', 'floating_network_id', 'router_id'

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
        return {'tenant_id': True, 'project_id': False}

    @property
    def resource_allowed_policy_target(self):
        # Neutron only supports policy for individual FIPs
        return None

    @property
    def service_type(self):
        return 'network'

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [{'term': {'tenant_id': request_context.owner}}]

    def get_objects(self):
        """Generator that lists all networks owned by all tenants."""
        neutron_client = openstack_clients.get_neutronclient()
        for fip in neutron_client.list_floatingips()['floatingips']:
            yield fip

    def serialize(self, floating_ip):
        return serialize_floatingip(floating_ip)
