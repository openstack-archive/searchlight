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
from searchlight.elasticsearch.plugins.cinder import serialize_cinder_volume
from searchlight.elasticsearch.plugins.cinder \
    import volumes_notification_handler
from searchlight.elasticsearch.plugins import openstack_clients

LOG = logging.getLogger(__name__)


# TODO(sjmc7): Parameterize once we have plugin configs
LIST_LIMIT = 100


class VolumeIndex(base.IndexBase):
    NotificationHandlerCls = volumes_notification_handler.VolumeHandler

    # Will be combined with 'admin_only_fields' from config
    ADMIN_ONLY_FIELDS = ['os-vol-mig-status-attr:*', 'os-vol-host-attr:*',
                         'migration_status']

    @classmethod
    def get_document_type(cls):
        return resource_types.CINDER_VOLUME

    def get_mapping(self):
        str_not_analyzed = {'type': 'string', 'index': 'not_analyzed'}
        return {
            'dynamic': True,
            'properties': {
                'attachments': {
                    'type': 'nested',
                    'properties': {
                        'attachment_id': str_not_analyzed,
                        'device': str_not_analyzed,
                        'host_name': str_not_analyzed,
                        'id': str_not_analyzed,
                        'server_id': str_not_analyzed,
                        'attached_at': {'type': 'date'}
                    }
                },
                'availability_zone': {'type': 'string',
                                      'index': 'not_analyzed'},
                'consistencygroup_id': {
                    'type': 'string', 'index': 'not_analyzed'
                },
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'bootable': {'type': 'boolean'},
                'created_at': {'type': 'date'},
                'description': {'type': 'string'},
                'encrypted': {'type': 'boolean'},
                'migration_status': {
                    'type': 'string', 'index': 'not_analyzed'},
                'multiattach': {'type': 'boolean'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'os-vol-host-attr:host': {
                    'type': 'string', 'index': 'not_analyzed'
                },
                'os-vol-mig-status-attr:migstat': {
                    'type': 'string', 'index': 'not_analyzed'
                },
                'os-vol-mig-status-attr:name_id': {
                    'type': 'string', 'index': 'not_analyzed'
                },
                'os-vol-tenant-attr:tenant_id': {
                    'type': 'string', 'index': 'not_analyzed'
                },
                'os-volume-replication:driver_data': {
                    'type': 'string', 'index': 'not_analyzed'
                },
                'os-volume-replication:extended_status': {
                    'type': 'string', 'index': 'not_analyzed'
                },
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'replication_status': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                # Using long here to consistent with glance.images
                'size': {'type': 'long'},
                'snapshot_id': {'type': 'string', 'index': 'not_analyzed'},
                'source_volid': {'type': 'string', 'index': 'not_analyzed'},
                'status': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string', 'index': 'not_analyzed'},
                'volume_type': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'updated_at': {'type': 'date'},
                'user_id': {'type': 'string', 'index': 'not_analyzed'},
            },
            "_meta": {
                "snapshot_id": {
                    "resource_type": resource_types.CINDER_SNAPSHOT
                },
                "tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "attachments.server_id": {
                    "resource_type": resource_types.NOVA_SERVER
                },
                "os-vol-tenant-attr:tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "user_id": {
                    "resource_type": resource_types.KEYSTONE_USER
                }
            }
        }

    @property
    def admin_only_fields(self):
        from_conf = super(VolumeIndex, self).admin_only_fields
        return VolumeIndex.ADMIN_ONLY_FIELDS + from_conf

    @property
    def facets_with_options(self):
        return ('status', 'availability_zone', 'bootable', 'volume_type',
                'encrypted', 'migration_status', 'replication_status',
                'multiattach')

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
        return {'os-vol-tenant-attr:tenant_id': True,
                'tenant_id': True,
                'migration_status': True,
                'os-vol-host-attr:host': True,
                'replication_status': True,
                'user_id': True,
                'os-vol-mig-status-attr:migstat': True,
                'os-vol-mig-status-attr:name_id': True,
                'os-volume-replication:driver_data': True,
                'os-volume-replication:extended_status': True,
                'source_volid': True,
                'migration_status': True}

    @property
    def resource_allowed_policy_target(self):
        return 'volume:get_all'

    @property
    def service_type(self):
        return 'volume'

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [
            {'term': {'project_id': request_context.owner}}
        ]

    def get_objects(self):
        """Generator that lists all cinder volumes owned by all tenants."""
        LOG.debug("Cinder volumes get_objects started")
        has_more = True
        marker = None
        while has_more:
            volumes = openstack_clients.get_cinderclient().volumes.list(
                limit=LIST_LIMIT,
                search_opts={'all_tenants': True},
                marker=marker
            )

            if not volumes:
                # Definitely no more; break straight away
                break

            # volumes.list always returns a list so we can grab the last id
            has_more = len(volumes) == LIST_LIMIT
            marker = volumes[-1].id

            for volume in volumes:
                yield volume

    def serialize(self, volume):
        return serialize_cinder_volume(volume)
