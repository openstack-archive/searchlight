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

import re

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.nova import serialize_nova_server
from searchlight.elasticsearch.plugins.nova \
    import servers_notification_handler
from searchlight.elasticsearch.plugins import openstack_clients


# TODO(sjmc7): Parameterize once we have plugin configs
LIST_LIMIT = 100


class ServerIndex(base.IndexBase):
    # Properties restricted to admins only. hostId seems not to be
    # considered sensitive because it doesn't directly identify hosts,
    # just whether your VMs are cohabiting
    ADMIN_ONLY_PROPERTIES = u'(OS-EXT-SRV-ATTR:.*)$'

    def __init__(self):
        super(ServerIndex, self).__init__()

    def get_index_name(self):
        return 'searchlight'

    def get_document_type(self):
        return 'OS::Nova::Server'

    def get_mapping(self):
        return {
            'dynamic': True,
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'name': {'type': 'string', 'index': 'not_analyzed'},
                'flavor': {
                    'type': 'nested',
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'owner': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string', 'index': 'not_analyzed'},
                'user_id': {'type': 'string', 'index': 'not_analyzed'},
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
                    'type': 'nested',
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'OS-EXT-AZ:availability_zone': {
                    'type': 'string',
                    'index': 'not_analyzed'
                },
                'OS-EXT-SRV-ATTR:host': {
                    'type': 'string',
                    'index': 'not_analyzed'
                },
                'security_groups': {
                    'type': 'nested',
                    'properties': {
                        'name': {'type': 'string'}
                    }
                },
                'status': {'type': 'string', 'index': 'not_analyzed'},
            },
        }

    @property
    def facets_with_options(self):
        return ('OS-EXT-AZ:availability_zone', 'OS-EXT-SRV-ATTR:host',
                'status', 'image.id', 'flavor.id', 'networks.name',
                'networks.OS-EXT-IPS:type', 'networks.version',
                'security_groups.name')

    @property
    def facets_excluded(self):
        """A map of {name: allow_admin} that indicate which
        fields should not be offered as facet options, or those that should
        only be available to administrators.
        """
        return {'OS-EXT-SRV-ATTR:host': True, 'tenant_id': True}

    def _get_rbac_field_filters(self, request_context):
        """Return any RBAC field filters to be injected into an indices
        query. Document type will be added to this list.
        """
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

    def filter_result(self, result, request_context):
        if not request_context.is_admin:
            hits = result['hits']['hits']
            for hit in hits:
                if hit['_type'] == self.get_document_type():
                    for key in list(hit['_source'].keys()):
                        if re.match(self.ADMIN_ONLY_PROPERTIES, key):
                            del hit['_source'][key]
        return result

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

    def get_notification_handler(self):
        return servers_notification_handler.InstanceHandler(
            self.engine,
            self.get_index_name(),
            self.get_document_type()
        )

    @staticmethod
    def get_notification_topic_exchanges():
        return (
            ('searchlight_indexer', 'nova'),
            ('searchlight_indexer', 'neutron')
        )

    def get_notification_supported_events(self):
        # TODO(sjmc7): DRY
        # Most events are duplicated by instance.update
        return [
            'compute.instance.update', 'compute.instance.exists',
            'compute.instance.create.end', 'compute.instance.delete.end',
            'compute.instance.power_on.end', 'compute.instance.power_off.end',
            'port.delete.end', 'port.create.end',
        ]
