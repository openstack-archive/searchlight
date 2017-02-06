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

from oslo_config import cfg

from searchlight.common import resource_types
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.swift import get_swift_objects
from searchlight.elasticsearch.plugins.swift import serialize_swift_object
from searchlight.elasticsearch.plugins.swift import swift_notification_handler

swift_plugin_opts = [
    cfg.StrOpt('reseller_prefix', default="AUTH_",
               help="prefix used in account names for auth system."),
]

CONF = cfg.CONF
CONF.register_opts(swift_plugin_opts, group='resource_plugin:os_swift_account')


class ObjectIndex(base.IndexBase):
    NotificationHandlerCls = swift_notification_handler.SwiftObjectHandler

    @classmethod
    def parent_plugin_type(cls):
        return resource_types.SWIFT_CONTAINER

    @classmethod
    def get_document_type(cls):
        return resource_types.SWIFT_OBJECT

    def get_mapping(self):
        return {
            'dynamic': True,
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
                'container': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    },
                },
                'container_id': {'type': 'string', 'index': 'not_analyzed'},
                'content_type': {'type': 'string', 'index': 'not_analyzed'},
                'content_length': {'type': 'long'},
                'etag': {'type': 'string'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'}
            },
            "_parent": {
                "type": self.parent_plugin_type()
            },
            "_meta": {
                "account_id": {
                    "resource_type": resource_types.SWIFT_ACCOUNT
                }
            }
        }

    @property
    def allow_admin_ignore_rbac(self):
        return False

    @classmethod
    def is_plugin_enabled_by_default(cls):
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
        account_plugin = self.parent_plugin.parent_plugin
        account_id = \
            account_plugin.options.reseller_prefix + request_context.owner

        return [
            {
                "has_parent": {
                    "type": self.parent_plugin_type(),
                    "query": {
                        "bool": {
                            "should": [
                                {'term': {'account_id': account_id}},
                                {'terms': {
                                    'x-container-read': [
                                        tenant_member,
                                        single_user
                                    ]
                                }}
                            ]
                        }
                    }
                }
            }
        ]

    def get_parent_id_field(self):
        return 'container_id'

    @property
    def routing_field(self):
        return "account_id"

    @property
    def facets_with_options(self):
        return ('container', 'content_type')

    def get_objects(self):
        return get_swift_objects()

    def serialize(self, obj):
        return serialize_swift_object(obj)
