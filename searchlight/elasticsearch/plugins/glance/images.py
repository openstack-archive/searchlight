# Copyright 2015 Intel Corporation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from searchlight.api import policy
from searchlight.common import property_utils
from searchlight.common import resource_types
from searchlight.common import utils
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.glance \
    import images_notification_handler
from searchlight.elasticsearch.plugins.glance import serialize_glance_image


class ImageIndex(base.IndexBase):
    NotificationHandlerCls = images_notification_handler.ImageHandler

    def __init__(self, policy_enforcer=None):
        super(ImageIndex, self).__init__()
        self.policy = policy_enforcer or policy.Enforcer()
        if property_utils.is_property_protection_enabled():
            self.property_rules = property_utils.PropertyRules(self.policy)
        self._image_base_properties = [
            'checksum', 'created_at', 'container_format', 'disk_format', 'id',
            'min_disk', 'min_ram', 'name', 'size', 'virtual_size', 'status',
            'tags', 'updated_at', 'visibility', 'protected', 'owner',
            'members', 'project_id']

    @classmethod
    def get_document_type(cls):
        return resource_types.GLANCE_IMAGE

    def get_mapping(self):
        return {
            'dynamic': True,
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'kernel_id': {'type': 'string', 'index': 'not_analyzed'},
                'ramdisk_id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'description': {'type': 'string'},
                'tags': {'type': 'string'},
                'disk_format': {'type': 'string'},
                'container_format': {'type': 'string'},
                'size': {'type': 'long'},
                'virtual_size': {'type': 'long'},
                'status': {'type': 'string', 'index': 'not_analyzed'},
                'visibility': {'type': 'string', 'index': 'not_analyzed'},
                'checksum': {'type': 'string'},
                'min_disk': {'type': 'long'},
                'min_ram': {'type': 'long'},
                'owner': {'type': 'string', 'index': 'not_analyzed'},
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'protected': {'type': 'boolean'},
                'members': {'type': 'string', 'index': 'not_analyzed'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'},

                # For images based on snapshot
                'image_type': {'type': 'string', 'index': 'not_analyzed'},
                'base_image_ref': {'type': 'string', 'index': 'not_analyzed'},
                'image_state': {'type': 'string', 'index': 'not_analyzed'},
                'user_id': {'type': 'string', 'index': 'not_analyzed'},
                'instance_uuid': {'type': 'string', 'index': 'not_analyzed'}
            },
            "_meta": {
                "owner": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "kernel_id": {
                    "resource_type": resource_types.GLANCE_IMAGE
                },
                "ramdisk_id": {
                    "resource_type": resource_types.GLANCE_IMAGE
                },
                "base_image_ref": {
                    "resource_type": resource_types.GLANCE_IMAGE
                },
                "user_id": {
                    "resource_type": resource_types.KEYSTONE_USER
                },
                "instance_uuid": {
                    "resource_type": resource_types.NOVA_SERVER
                },
            }
        }

    @property
    def facets_with_options(self):
        return ('disk_format', 'container_format', 'tags', 'visibility',
                'protected', 'status', 'image_type', 'image_state')

    @property
    def facets_excluded(self):
        return {'owner': True, 'project_id': True}

    @property
    def resource_allowed_policy_target(self):
        return 'get_images'

    @property
    def service_type(self):
        return 'image'

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'owner': request_context.owner}},
            {'term': {'visibility': 'public'}},
            {'term': {'members': request_context.tenant}}
        ]

    def filter_result(self, hit, request_context):
        super(ImageIndex, self).filter_result(hit, request_context)
        highlight = hit.get('highlight')
        if highlight:
            utils.restore_dots_in_field_names(highlight)
        source = hit['_source']
        utils.restore_dots_in_field_names(source)
        if property_utils.is_property_protection_enabled():
            for key in list(source.keys()):
                if key not in self._image_base_properties:
                    if not self.property_rules.check_property_rules(
                            key, 'read', request_context):
                        del source[key]

        # Strip out the members list for non-admins or non-owners. The glance
        # api leaves just the current tenant in the list for non-admins
        if not (request_context.is_admin or
                source['owner'] == request_context.tenant):
            if source.get('members', []):
                # Remove any members that don't match the current tenant
                source['members'] = list(filter(
                    lambda m: m == request_context.tenant,
                    source['members']))

    def get_objects(self):
        from searchlight.elasticsearch.plugins import openstack_clients
        # Images include their properties and tags. Members are different
        return openstack_clients.get_glanceclient().images.list()

    def serialize(self, obj):
        return serialize_glance_image(obj)
