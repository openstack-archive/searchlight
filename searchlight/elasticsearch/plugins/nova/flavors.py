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
from searchlight.elasticsearch.plugins.nova import FLAVOR_ACCESS_FIELD
from searchlight.elasticsearch.plugins.nova \
    import notification_handler
from searchlight.elasticsearch.plugins.nova import serialize_nova_flavor
from searchlight.elasticsearch.plugins import openstack_clients


class FlavorIndex(base.IndexBase):

    NotificationHandlerCls = notification_handler.FlavorHandler

    @classmethod
    def get_document_type(cls):
        return resource_types.NOVA_FLAVOR

    def get_mapping(self):
        string_not_analyzed = {'type': 'string', 'index': 'not_analyzed'}
        integer = {'type': 'integer'}
        return {
            'dynamic': True,
            'properties': {
                'id': string_not_analyzed,
                'tenant_id': string_not_analyzed,
                'OS-FLV-DISABLED:disabled': {'type': 'boolean'},
                'OS-FLV-EXT-DATA:ephemeral': integer,
                'disk': integer,
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': string_not_analyzed
                    }
                },
                'os-flavor-access:is_public': {'type': 'boolean'},
                FLAVOR_ACCESS_FIELD: string_not_analyzed,
                'ram': integer,
                'rxtx_factor': {'type': 'float'},
                'swap': string_not_analyzed,
                'vcpus': integer,
                'extra-specs': {
                    'type': 'object',
                    'properties': {}
                }
            }
        }

    def get_objects(self):
        """Generator that lists all nova Flavors"""
        return openstack_clients.get_novaclient().flavors.list(is_public=None)

    @property
    def facets_with_options(self):
        return ('OS-FLV-DISABLED:disabled', 'os-flavor-access:is_public')

    @property
    def resource_allowed_policy_target(self):
        return 'os_compute_api:flavors'

    @property
    def service_type(self):
        return 'compute'

    def serialize(self, flavor):
        return serialize_nova_flavor(flavor)

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [
            {'term': {'os-flavor-access:is_public': True}},
            {'term': {FLAVOR_ACCESS_FIELD: request_context.tenant}}
        ]

    def filter_result(self, hit, request_context):
        super(FlavorIndex, self).filter_result(hit, request_context)
        # Only admins and tenants who the flavor has been granted
        # access can see the full list of access.
        if not request_context.is_admin:
            source = hit['_source']
            is_public = source.get('os-flavor-access:is_public', False)
            access = source.get(FLAVOR_ACCESS_FIELD, [])
            if is_public or request_context.tenant not in access:
                source.pop(FLAVOR_ACCESS_FIELD, None)
