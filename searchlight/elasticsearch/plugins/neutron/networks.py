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

from collections import defaultdict
from searchlight.common import resource_types
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.neutron import add_rbac
from searchlight.elasticsearch.plugins.neutron import notification_handlers
from searchlight.elasticsearch.plugins.neutron import serialize_network
from searchlight.elasticsearch.plugins import openstack_clients


class NetworkIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.NetworkHandler

    ADMIN_ONLY_FIELDS = ['provider:*']

    def __init__(self):
        super(NetworkIndex, self).__init__()

    @classmethod
    def get_document_type(cls):
        return resource_types.NEUTRON_NETWORK

    def get_mapping(self):
        return {
            'dynamic': False,
            'properties': {
                # Availability zones are not present because they're not
                # contained in notifications
                'admin_state_up': {'type': 'boolean'},
                'availability_zone_hints': {'type': 'string',
                                            'index': 'not_analyzed'},
                'availability_zones': {'type': 'string',
                                       'index': 'not_analyzed'},
                'created_at': {'type': 'date'},
                'description': {'type': 'string'},
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'ipv4_address_scope': {'type': 'string',
                                       'index': 'not_analyzed'},
                'ipv6_address_scope': {'type': 'string',
                                       'index': 'not_analyzed'},
                'mtu': {'type': 'integer'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'port_security_enabled': {'type': 'boolean'},
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'provider:network_type': {'type': 'string'},
                'provider:physical_network': {'type': 'string'},
                'provider:segmentation_id': {'type': 'integer'},
                'router:external': {'type': 'boolean'},
                'shared': {'type': 'boolean'},
                'status': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string', 'index': 'not_analyzed'},
                'members': {'type': 'string', 'index': 'not_analyzed'},
                'rbac_policy': {
                    'type': 'nested',
                    'properties': {
                        'rbac_id': {'type': 'string', 'index': 'not_analyzed'},
                        'tenant': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'updated_at': {'type': 'date'}
            },
            "_meta": {
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                }
            }
        }

    @property
    def admin_only_fields(self):
        from_conf = super(NetworkIndex, self).admin_only_fields
        return from_conf + NetworkIndex.ADMIN_ONLY_FIELDS

    @property
    def facets_with_options(self):
        return ('provider:network_type', 'provider:physical_network', 'status',
                'port_security_enabled', 'shared', 'availability_zones')

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
        return {'tenant_id': True, 'project_id': True}

    @property
    def resource_allowed_policy_target(self):
        # Neutron only supports policy for individual networks
        return None

    @property
    def service_type(self):
        return 'network'

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [
            {'term': {'tenant_id': request_context.owner}},
            {'terms': {'members': [request_context.owner, '*']}},
            {'term': {'router:external': True}},
            {'term': {'shared': True}}
        ]

    def get_rbac_policies(self):
        policies = defaultdict(list)
        policy_list = self.get_rbac_objects()
        for policy in policy_list:
            policies[policy['object_id']].append(policy)
        return policies

    def get_objects(self):
        """Generator that lists all networks owned by all tenants."""
        # Neutronclient handles pagination itself; list_networks is a generator
        policies = self.get_rbac_policies()
        neutron_client = openstack_clients.get_neutronclient()
        for network in neutron_client.list_networks()['networks']:
            network['members'] = []
            network['rbac_policy'] = []
            for policy in policies[network['id']]:
                add_rbac(network, policy['target_tenant'], policy['id'])
            yield network

    def serialize(self, network):
        return serialize_network(network)

    def filter_result(self, hit, request_context):
        # The mapping contains internal fields related to RBAC policy.
        # Remove them.
        source = hit['_source']
        source.pop('rbac_policy', None)
        source.pop('members', None)

    def get_rbac_objects(self):
        """Generator that lists all RBAC policies for all tenants."""
        valid_actions = notification_handlers.RBAC_VALID_ACTIONS
        neutron_client = openstack_clients.get_neutronclient()
        policies = neutron_client.list_rbac_policies()['rbac_policies']
        for policy in [p for p in policies if
                       p['object_type'] == 'network' and
                       p['action'] in valid_actions]:
            yield policy
