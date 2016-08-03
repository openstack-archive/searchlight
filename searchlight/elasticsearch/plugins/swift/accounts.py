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
from searchlight.elasticsearch.plugins.swift import get_swift_accounts
from searchlight.elasticsearch.plugins.swift import serialize_swift_account
from searchlight.elasticsearch.plugins.swift import swift_notification_handler

swift_plugin_opts = [
    cfg.StrOpt('reseller_prefix', default="AUTH_",
               help="prefix used in account names for auth system."),
]

CONF = cfg.CONF
CONF.register_opts(swift_plugin_opts, group='resource_plugin:os_swift_account')


class AccountIndex(base.IndexBase):
    NotificationHandlerCls = swift_notification_handler.SwiftAccountHandler

    def __init__(self):
        super(AccountIndex, self).__init__()
        self.options = cfg.CONF[self.get_config_group_name()]

    # swift_owner_headers
    ADMIN_ONLY_FIELDS = ['x-account-meta-temp-url-key',
                         'x-account-meta-temp-url-key-2',
                         'x-account-access-control']

    @classmethod
    def get_document_type(cls):
        return resource_types.SWIFT_ACCOUNT

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
                # TODO(lakshmiS): Removing following field(s) since account
                # notifications don't include it for subsequent updates.
                # Enable when it is included in future notifications.

                # The number of objects in the account.
                # 'x-account-object-count': {'type': 'long'},

                # The total number of bytes that are stored in Object Storage
                #  for the account.
                # 'x-account-bytes-used': {'type': 'long'},

                # The number of containers.
                # 'x-account-container-count': {'type': 'long'},

                'domain_id': {'type': 'string', 'index': 'not_analyzed'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'}
            },
        }

    @property
    def admin_only_fields(self):
        from_conf = super(AccountIndex, self).admin_only_fields
        return AccountIndex.ADMIN_ONLY_FIELDS + from_conf

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
        id = self.options.reseller_prefix + request_context.owner
        return [
            {"term": {"id": id}}
        ]

    @property
    def routing_field(self):
        return "id"

    def get_objects(self):
        return get_swift_accounts(self.options.reseller_prefix)

    def serialize(self, obj):
        return serialize_swift_account(obj)
