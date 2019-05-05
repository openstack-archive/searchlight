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


# chassis is not mandatory for node, and it is not parent plugin
class ChassisIndex(base.IndexBase):
    NotificationHandlerCls = notification_handlers.ChassisHandler

    @classmethod
    def get_document_type(cls):
        return resource_types.IRONIC_CHASSIS

    def get_mapping(self):
        return copy.deepcopy(resources.CHASSIS_MAPPING)

    @property
    def admin_only_fields(self):
        return []

    def get_document_id_field(self):
        return 'uuid'

    @property
    def resource_allowed_policy_target(self):
        return 'baremetal:chassis:get'

    @property
    def service_type(self):
        return 'baremetal'

    def _get_rbac_field_filters(self, request_context):
        return []

    def get_objects(self):
        """Generator that lists all chassis."""
        ironic_client = openstack_clients.get_ironicclient()
        for chassis in ironic_client.chassis.list(detail=True, limit=0):
            yield chassis

    def serialize(self, chassis):
        chassis_dict = chassis.to_dict()
        return serialize_resource(chassis_dict, resources.CHASSIS_FIELDS)
