# Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
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
from searchlight.elasticsearch.plugins.nova import serialize_nova_server
from searchlight.elasticsearch.plugins import openstack_clients


# TODO(sjmc7): Parameterize once we have plugin configs
LIST_LIMIT = 100


class ServerIndex(base.IndexBase):
    NotificationHandlerCls = notification_handler.InstanceHandler

    # Will be combined with 'admin_only_fields' from config
    # https://docs.openstack.org/api-ref/compute/?expanded=show-server-details-detail
    ADMIN_ONLY_FIELDS = ['OS-EXT-SRV-ATTR:*', 'host_status']

    @classmethod
    def get_document_type(cls):
        return resource_types.NOVA_SERVER

    def get_mapping(self):
        return {
            'dynamic': True,
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'flavor': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'owner': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string', 'index': 'not_analyzed'},
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'user_id': {'type': 'string', 'index': 'not_analyzed'},
                'created': {'type': 'date'},
                'updated': {'type': 'date'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'},
                'networks': {
                    'type': 'nested',
                    'properties': {
                        'name': {'type': 'string'},
                        'version': {'type': 'short'},
                        'OS-EXT-IPS-MAC:mac_addr': {
                            'type': 'string',
                            'index': 'not_analyzed'
                        },
                        'OS-EXT-IPS:type': {
                            'type': 'string',
                            'index': 'not_analyzed'
                        },
                        'ipv4_addr': {'type': 'ip'},
                        'ipv6_addr': {
                            'type': 'string',
                            'index': 'not_analyzed'
                        }
                    }
                },
                'image': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'OS-EXT-AZ:availability_zone': {
                    'type': 'string',
                    'index': 'not_analyzed'
                },
                'OS-EXT-SRV-ATTR:hypervisor_hostname': {
                    'type': 'string',
                    'index': 'not_analyzed'
                },
                'OS-EXT-STS:vm_state': {
                    'type': 'string',
                    'index': 'not_analyzed'
                },
                'fault': {
                    'type': 'object',
                    'properties': {
                        'code': {'type': 'integer'},
                        'created': {'type': 'date'},
                        'message': {'type': 'string'},
                    }
                },
                # Nova gives security group names, where neutron ports
                # give ids in the same field. There's no solution that
                # maintains compatibility with both
                'security_groups': {'type': 'string', 'index': 'not_analyzed'},
                'status': {'type': 'string', 'index': 'not_analyzed'},
                # Nova adds/removes fields using microversion mechanism, check
                # https://opendev.org/openstack/nova/src/branch/master/nova/api/openstack/compute/rest_api_version_history.rst
                # for detailed Nova microversion history.
                # Added in microversion 2.9
                'locked': {'type': 'string', 'index': 'not_analyzed'},
                # Added in microversion 2.16
                'host_status': {'type': 'string', 'index': 'not_analyzed'},
                # Added in microversion 2.19
                'description': {'type': 'string'},
                # Added in microversion 2.26
                'tags': {'type': 'string'},
            },
            "_meta": {
                "image.id": {
                    "resource_type": resource_types.GLANCE_IMAGE
                },
                "flavor.id": {
                    "resource_type": resource_types.NOVA_FLAVOR
                },
                "tenant_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "user_id": {
                    "resource_type": resource_types.KEYSTONE_USER
                },
                "OS-EXT-AZ:availability_zone": {
                    "resource_type": resource_types.NOVA_AVAILABILITY_ZONE
                },
                "security_groups": {
                    "resource_type": resource_types.NOVA_SECURITY_GROUP
                },
                "locked": {
                    "min_version": "2.9"
                },
                "host_status": {
                    "min_version": "2.16"
                },
                "description": {
                    "min_version": "2.19"
                },
                "tags": {
                    "min_version": "2.26"
                }
            },
        }

    @property
    def admin_only_fields(self):
        from_conf = super(ServerIndex, self).admin_only_fields
        return ServerIndex.ADMIN_ONLY_FIELDS + from_conf

    @property
    def facets_with_options(self):
        return ('OS-EXT-AZ:availability_zone',
                'status', 'image.id', 'flavor.id', 'networks.name',
                'networks.OS-EXT-IPS:type', 'networks.version',
                'security_groups', 'host_status', 'locked')

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
        return {'tenant_id': True, 'project_id': True, 'host_status': True,
                'created': False, 'updated': False,
                'OS-EXT-SRV-ATTR:hypervisor_hostname': True, 'fault': False}

    @property
    def resource_allowed_policy_target(self):
        return 'os_compute_api:servers:index'

    @property
    def service_type(self):
        return 'compute'

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [
            {'term': {'tenant_id': request_context.owner}},
        ]

    def get_objects(self):
        """Generator that lists all nova servers owned by all tenants."""
        has_more = True
        marker = None
        while has_more:
            servers = openstack_clients.get_novaclient().servers.list(
                limit=LIST_LIMIT,
                search_opts={'all_tenants': True},
                marker=marker
            )

            if not servers:
                # Definitely no more; break straight away
                break

            # servers.list always returns a list so we can grab the last id
            has_more = len(servers) == LIST_LIMIT
            marker = servers[-1].id

            for server in servers:
                yield server

    def serialize(self, server):
        return serialize_nova_server(server)

    def filter_result(self, hit, request_context):
        super(ServerIndex, self).filter_result(hit, request_context)

        # Reverse the change we make to security groups in serialize() to
        # maintain compatibility with the nova API response
        source = hit['_source']
        security_groups = source.pop('security_groups', None)
        if security_groups is not None:
            source['security_groups'] = [{"name": sg}
                                         for sg in security_groups]
