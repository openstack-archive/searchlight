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
from searchlight.elasticsearch.plugins.neutron import serialize_security_group
from searchlight.elasticsearch.plugins import openstack_clients


class SecurityGroupIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.SecurityGroupHandler

    @classmethod
    def get_document_type(cls):
        return resource_types.NEUTRON_SECURITY_GROUP

    def get_mapping(self):
        string_not_analyzed = {'type': 'string', 'index': 'not_analyzed'}
        ordered_string = {'type': 'string',
                          'fields': {'raw': string_not_analyzed}}

        return {
            'dynamic': False,
            'properties': {
                'security_group_rules': {
                    'type': 'nested',
                    'properties': {
                        'remote_group_id': string_not_analyzed,
                        'direction': {'type': 'string'},
                        'protocol': {'type': 'string'},
                        'description': {'type': 'string'},
                        'ethertype': {'type': 'string'},
                        'remote_ip_prefix': {'type': 'string'},
                        'port_range_max': {'type': 'integer'},
                        'port_range_min': {'type': 'integer'},
                        'security_group_id': string_not_analyzed,
                        'tenant_id': string_not_analyzed,
                        'id': string_not_analyzed,
                    },
                },
                'id': string_not_analyzed,
                'project_id': string_not_analyzed,
                'tenant_id': string_not_analyzed,
                'name': ordered_string,
                'description': {'type': 'string'},
            },
            "_meta": {
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
            }
        }

    @property
    def facets_with_options(self):
        return ('security_group_rules.direction',
                'security_group_rules.ethertype')

    @property
    def facets_excluded(self):
        return {'project_id': True, 'tenant_id': True}

    @property
    def resource_allowed_policy_target(self):
        # Neutron only supports policy for individual resources
        return None

    @property
    def service_type(self):
        return 'network'

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

    def get_objects(self):
        """Generator that lists all security groups."""
        neutron_client = openstack_clients.get_neutronclient()
        for group in neutron_client.list_security_groups()['security_groups']:
            yield group

    def serialize(self, sec_group):
        return serialize_security_group(sec_group)
