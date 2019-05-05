# Copyright (c) 2016 Huawei Technology Ltd.
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
from searchlight.elasticsearch.plugins.nova \
    import notification_handler
from searchlight.elasticsearch.plugins.nova import serialize_nova_servergroup
from searchlight.elasticsearch.plugins import openstack_clients


class ServerGroupIndex(base.IndexBase):
    NotificationHandlerCls = notification_handler.ServerGroupHandler

    @classmethod
    def get_document_type(cls):
        return resource_types.NOVA_SERVERGROUP

    def get_mapping(self):
        return {
            'dynamic': True,
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'user_id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'policies': {'type': 'string', 'index': 'not_analyzed'},
                'members': {'type': 'string', 'index': 'not_analyzed'},
                'updated_at': {'type': 'date'},
                'metadata': {'type': 'object', 'properties': {}}
            },
            "_meta": {
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "user_id": {
                    "resource_type": resource_types.KEYSTONE_USER
                },
            }
        }

    @property
    def facets_with_options(self):
        return 'policies'

    @property
    def service_type(self):
        return 'compute'

    @property
    def resource_allowed_policy_target(self):
        return 'compute_extension:server_groups'

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [
            {'term': {'project_id': request_context.owner}},
        ]

    def get_objects(self):
        """Generator that lists all nova server groups."""
        for group in openstack_clients.get_novaclient(
        ).server_groups.list(all_projects=True):
            yield group

    def serialize(self, servergroup):
        return serialize_nova_servergroup(servergroup)
