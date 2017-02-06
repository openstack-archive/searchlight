# Copyright (c) 2016 Hewlett-Packard Development Company, L.P.
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
from searchlight.elasticsearch.plugins.swift import get_swift_containers
from searchlight.elasticsearch.plugins.swift import serialize_swift_container
from searchlight.elasticsearch.plugins.swift import swift_notification_handler


class ContainerIndex(base.IndexBase):
    NotificationHandlerCls = swift_notification_handler.SwiftContainerHandler

    def get_notification_handler(self):
        """Override because the container handler needs a handle to object
        indexer for cascade delete of container to objects.
        """
        return self.NotificationHandlerCls(
            self.index_helper,
            self.options,
            object_helper=self.child_plugins[0].index_helper)

    # swift_owner_headers
    ADMIN_ONLY_FIELDS = ['x-container-write',
                         'x-container-sync-key',
                         'x-container-sync-to',
                         'x-container-meta-temp-url-key',
                         'x-container-meta-temp-url-key-2']

    @classmethod
    def parent_plugin_type(cls):
        return resource_types.SWIFT_ACCOUNT

    @classmethod
    def get_document_type(cls):
        return resource_types.SWIFT_CONTAINER

    def get_mapping(self):
        return {
            'dynamic': True,
            "_source": {
                "excludes": ["x-container-read"]
            },
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    },
                },
                'account': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    },
                },
                'account_id': {'type': 'string', 'index': 'not_analyzed'},
                'x-container-read': {
                    'type': 'string', 'index': 'not_analyzed',
                    'store': False
                },

                # TODO(lakshmiS): Removing following field(s) since account
                # notifications don't include it for subsequent updates.
                # Enable when it is included in future notifications.
                # 'x-container-object-count': {'type': 'long'},
                # 'x-container-bytes-used': {'type': 'long'},

                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'}
            },
            "_parent": {
                "type": self.parent_plugin_type()
            }
        }

    @property
    def admin_only_fields(self):
        from_conf = super(ContainerIndex, self).admin_only_fields
        return ContainerIndex.ADMIN_ONLY_FIELDS + from_conf

    @classmethod
    def is_plugin_enabled_by_default(cls):
        return False

    @property
    def allow_admin_ignore_rbac(self):
        return False

    @property
    def resource_allowed_policy_target(self):
        return None

    @property
    def service_type(self):
        return None

    def _get_rbac_field_filters(self, request_context):
        tenant_member = request_context.tenant + ":*"
        single_user = request_context.tenant + ":" + request_context.user
        account_id = \
            self.parent_plugin.options.reseller_prefix + request_context.owner

        return [
            {'term': {'account_id': account_id}},
            {'terms': {'x-container-read': [tenant_member, single_user]}}
        ]

    def get_parent_id_field(self):
        return 'account_id'

    @property
    def routing_field(self):
        return "account_id"

    def get_objects(self):
        return get_swift_containers()

    def serialize(self, obj):
        return serialize_swift_container(obj)
