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

from oslo_log import log as logging

from searchlight.common import resource_types
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.cinder import serialize_cinder_snapshot
from searchlight.elasticsearch.plugins.cinder import \
    snapshots_notification_handler
from searchlight.elasticsearch.plugins import openstack_clients

LOG = logging.getLogger(__name__)


# TODO(sjmc7): Parameterize once we have plugin configs
LIST_LIMIT = 100


class SnapshotIndex(base.IndexBase):
    NotificationHandlerCls = snapshots_notification_handler.SnapshotHandler

    ADMIN_ONLY_FIELDS = []

    @classmethod
    def get_document_type(cls):
        """Unusually, this doesn't have a heat resource type equivalent"""
        return resource_types.CINDER_SNAPSHOT

    @classmethod
    def parent_plugin_type(cls):
        return resource_types.CINDER_VOLUME

    def get_parent_id_field(self):
        return 'volume_id'

    @property
    def resource_allowed_policy_target(self):
        return 'volume:get_all_snapshots'

    @property
    def service_type(self):
        return 'volume'

    @property
    def requires_role_separation(self):
        # TODO(sjmc7) Remove once this is abstracted
        return self.parent_plugin.requires_role_separation

    def get_mapping(self):
        return {
            'dynamic': True,
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'description': {'type': 'string'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'os-extended-snapshot-attributes:progress':
                    {'type': 'string', 'index': 'not_analyzed'},
                'os-extended-snapshot-attributes:project_id':
                    {'type': 'string', 'index': 'not_analyzed'},
                'user_id': {'type': 'string', 'index': 'not_analyzed'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'},
                'status': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string', 'index': 'not_analyzed'},
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'volume_id': {'type': 'string', 'index': 'not_analyzed'},
            },
            "_meta": {
                "tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "os-extended-snapshot-attributes:project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "user_id": {
                    "resource_type": resource_types.KEYSTONE_USER
                }
            }
        }

    @property
    def admin_only_fields(self):
        from_conf = super(SnapshotIndex, self).admin_only_fields
        return SnapshotIndex.ADMIN_ONLY_FIELDS + from_conf

    @property
    def facets_with_options(self):
        return ('status',)

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
        # FIXME: DuncanT: Need to go through these carefully
        return {'user_id': True,
                'tenant_id': True,
                'os-extended-snapshot-attributes:project_id': False}

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [
            {'term': {'project_id': request_context.owner}}
        ]

    def get_objects(self):
        """Generator that lists all cinder snapshots owned by all tenants."""
        LOG.debug("Cinder snapshots get_objects started")
        has_more = True
        marker = None
        cc = openstack_clients.get_cinderclient()
        while has_more:
            snapshots = cc.volume_snapshots.list(
                limit=LIST_LIMIT,
                search_opts={'all_tenants': True},
                marker=marker
            )

            if not snapshots:
                # Definitely no more; break straight away
                break

            # snapshots.list always returns a list so we can grab the last id
            has_more = len(snapshots) == LIST_LIMIT
            marker = snapshots[-1].id

            for snapshot in snapshots:
                yield snapshot

    def serialize(self, snapshot):
        return serialize_cinder_snapshot(snapshot)
