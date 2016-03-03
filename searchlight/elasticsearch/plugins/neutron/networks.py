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

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.neutron import notification_handlers
from searchlight.elasticsearch.plugins.neutron import serialize_network
from searchlight.elasticsearch.plugins import openstack_clients


class NetworkIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.NetworkHandler

    ADMIN_ONLY_FIELDS = ['provider:*']

    @classmethod
    def get_document_type(self):
        return 'OS::Neutron::Net'

    def get_mapping(self):
        return {
            'dynamic': 'false',
            'properties': {
                'admin_state_up': {'type': 'boolean'},
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'provider:network_type': {'type': 'string'},
                'provider:physical_network': {'type': 'string'},
                'provider:segmentation_id': {'type': 'integer'},
                'router:external': {'type': 'boolean'},
                'shared': {'type': 'boolean'},
                'status': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string', 'index': 'not_analyzed'},
                'updated_at': {'type': 'string', 'index': 'not_analyzed'}
            }
        }

    @property
    def admin_only_fields(self):
        from_conf = super(NetworkIndex, self).admin_only_fields
        return from_conf + NetworkIndex.ADMIN_ONLY_FIELDS

    @property
    def facets_with_options(self):
        return ('provider:network_type', 'provider:physical_network', 'status')

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
        return {'tenant_id': True}

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [{
            'bool': {
                'should': [
                    {'term': {'tenant_id': request_context.owner}},
                    {'term': {'router:external': True}},
                    {'term': {'shared': True}}
                ]
            }
        }]

    def get_objects(self):
        """Generator that lists all networks owned by all tenants."""
        # Neutronclient handles pagination itself; list_networks is a generator
        neutron_client = openstack_clients.get_neutronclient()
        for network in neutron_client.list_networks()['networks']:
            yield network

    def serialize(self, network):
        return serialize_network(network)
