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

from searchlight.common import resource_types
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.ironic import notification_handlers
from searchlight.elasticsearch.plugins.ironic import resources
from searchlight.elasticsearch.plugins.ironic import serialize_resource
from searchlight.elasticsearch.plugins import openstack_clients


class NodeIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.NodeHandler

    def get_notification_handler(self):
        return self.NotificationHandlerCls(
            self.index_helper,
            self.options,
            port_helper=self.child_plugins[0].index_helper)

    @classmethod
    def get_document_type(cls):
        return resource_types.IRONIC_NODE

    def get_mapping(self):
        return copy.deepcopy(resources.NODE_MAPPING)

    @property
    def admin_only_fields(self):
        return []

    def get_document_id_field(self):
        return 'uuid'

    @property
    def facets_with_options(self):
        return ('power_state', 'target_power_state', 'provision_state',
                'target_provision_state', 'maintenance', 'console_enabled')

    @property
    def resource_allowed_policy_target(self):
        return 'baremetal:node:get'

    @property
    def service_type(self):
        return 'baremetal'

    def _get_rbac_field_filters(self, request_context):
        return []

    def get_objects(self):
        """Generator that lists all nodes."""
        ironic_client = openstack_clients.get_ironicclient()
        for node in ironic_client.node.list(detail=True, limit=0):
            yield node

    def serialize(self, node):
        node_dict = node.to_dict()
        return serialize_resource(node_dict, resources.NODE_FIELDS)
