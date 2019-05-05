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
from searchlight.elasticsearch.plugins.neutron import serialize_router
from searchlight.elasticsearch.plugins import openstack_clients


class RouterIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.RouterHandler

    ADMIN_ONLY_FIELDS = ['distributed', 'ha']

    @classmethod
    def get_document_type(cls):
        return resource_types.NEUTRON_ROUTER

    def get_mapping(self):
        return {
            'dynamic': 'false',
            'properties': {
                'admin_state_up': {'type': 'boolean'},
                'availability_zone_hints': {'type': 'string',
                                            'index': 'not_analyzed'},
                'availability_zones': {'type': 'string',
                                       'index': 'not_analyzed'},
                # Routers don't have created_at
                'description': {'type': 'string'},
                'distributed': {'type': 'boolean'},
                'external_gateway_info': {
                    'type': 'nested',
                    'properties': {
                        'enable_snat': {'type': 'boolean'},
                        'external_fixed_ips': {
                            'type': 'nested',
                            # TODO(sjmc7) Check we can deal with arbitrary
                            # levels of nesting with facets
                            'properties': {
                                'ip_address': {'type': 'string',
                                               'index': 'not_analyzed'},
                                'subnet_id': {'type': 'string',
                                              'index': 'not_analyzed'},
                            }
                        },
                        'network_id': {'type': 'string',
                                       'index': 'not_analyzed'}
                    }
                },
                'ha': {'type': 'boolean'},
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                # TODO(sjmc7) Decide whether to keep these;
                # they seem like trouble
                'routes': {
                    'type': 'nested',
                    'properties': {
                        'destination': {'type': 'string',
                                        'index': 'not_analyzed'},
                        'nexthop': {'type': 'string', 'index': 'not_analyzed'},
                        'action': {'type': 'string', 'index': 'not_analyzed'},
                        'source': {'type': 'string',
                                   'index': 'not_analyzed'}
                    }
                },
                'status': {'type': 'string', 'index': 'not_analyzed'},
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
                "external_gateway_info.external_fixed_ips.subnet_id": {
                    "resource_type": resource_types.NEUTRON_SUBNET
                },
                "external_gateway_info.network_id": {
                    "resource_type": resource_types.NEUTRON_NETWORK
                }
            }
        }

    @property
    def admin_only_fields(self):
        from_conf = super(RouterIndex, self).admin_only_fields
        return from_conf + RouterIndex.ADMIN_ONLY_FIELDS

    @property
    def facets_with_options(self):
        return ('admin_state_up', 'availability_zones', 'status',
                'distributed', 'ha', 'external_gateway_info.enable_snat')

    @property
    def facets_excluded(self):
        return {'tenant_id': True, 'distributed': True, 'ha': True,
                'project_id': True}

    @property
    def resource_allowed_policy_target(self):
        # Neutron only supports policy for individual routers
        return None

    @property
    def service_type(self):
        return 'network'

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

    def get_objects(self):
        neutron_client = openstack_clients.get_neutronclient()
        for router in neutron_client.list_routers()['routers']:
            yield router

    def serialize(self, router):
        return serialize_router(router)
