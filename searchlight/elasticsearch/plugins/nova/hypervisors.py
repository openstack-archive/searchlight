# Copyright (c) 2016 Kylin Cloud
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
from searchlight.elasticsearch.plugins.nova import serialize_nova_hypervisor
from searchlight.elasticsearch.plugins import openstack_clients


class HypervisorIndex(base.IndexBase):

    @classmethod
    def get_document_type(cls):
        return resource_types.NOVA_HYPERVISOR

    def get_mapping(self):
        string_not_analyzed = {'type': 'string', 'index': 'not_analyzed'}
        integer = {'type': 'integer'}
        long_not_analyzed = {'type': 'long', 'index': 'not_analyzed'}
        # Hypervisor doesn't have updated_at and created_at.
        return {
            'dynamic': False,
            'properties': {
                'id': string_not_analyzed,
                'service': {
                    'type': 'object',
                    'properties': {
                        'id': integer,
                        'host': string_not_analyzed,
                        'disabled_reason': {'type': 'string'},
                    }
                },
                'cpu_info': {
                    'type': 'object',
                    'properties': {
                        'vendor': string_not_analyzed,
                        'model': string_not_analyzed,
                        'arch': string_not_analyzed,
                        'features': string_not_analyzed,
                        'topology': {
                            'type': 'object',
                            'properties': {
                                'cores': integer,
                                'threads': integer,
                                'sockets': integer,
                            }
                        }
                    }
                },
                'state': string_not_analyzed,
                'status': string_not_analyzed,
                'vcpus': integer,
                'memory_mb': long_not_analyzed,
                'local_gb': long_not_analyzed,
                'hypervisor_version': integer,
                'hypervisor_type': string_not_analyzed,
                'disk_available_least': integer,
                'hypervisor_hostname': string_not_analyzed,
                'host_ip': string_not_analyzed,
            },
        }

    @property
    def admin_only_fields(self):
        # Since this whole plugin is admin only, this can return an empty list.
        return []

    @property
    def facets_with_options(self):
        return ('status', 'state', 'hypervisor_version', 'hypervisor_type',
                'vcpus', 'memory_mb', 'local_gb')

    @property
    def resource_allowed_policy_target(self):
        return 'os_compute_api:os-hypervisors'

    @property
    def service_type(self):
        return 'compute'

    def _get_rbac_field_filters(self, request_context):
        # Hypervisors don't belong to a tenant; there won't be any RBAC
        # filter for hypervisors.
        return []

    def get_objects(self):
        """Generator that lists all nova hypervisors."""
        return openstack_clients.get_novaclient().hypervisors.list()

    def serialize(self, hypervisor):
        return serialize_nova_hypervisor(hypervisor)
