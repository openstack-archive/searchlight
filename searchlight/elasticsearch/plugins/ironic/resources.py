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

# based on full set of fields payload version 1.0
NODE_MAPPING = {
    'dynamic': False,
    'properties': {
        # "id" field does not present in ironic API resource, this is a
        # copy of "uuid"
        'id': {'type': 'string', 'index': 'not_analyzed'},
        'uuid': {'type': 'string', 'index': 'not_analyzed'},
        'name': {
            'type': 'string',
            'fields': {
                'raw': {'type': 'string', 'index': 'not_analyzed'}
            }
        },
        'chassis_uuid': {'type': 'string', 'index': 'not_analyzed'},
        'instance_uuid': {'type': 'string', 'index': 'not_analyzed'},
        'driver': {'type': 'string', 'index': 'not_analyzed'},
        'driver_info': {'type': 'object', 'dynamic': True, 'properties': {}},
        'clean_step': {'type': 'object', 'dynamic': True, 'properties': {}},
        'instance_info': {'type': 'object', 'dynamic': True, 'properties': {}},
        # mapped "properties" field
        'node_properties': {
            'type': 'object', 'dynamic': True, 'properties': {}
        },
        'power_state': {'type': 'string', 'index': 'not_analyzed'},
        'target_power_state': {'type': 'string', 'index': 'not_analyzed'},
        'provision_state': {'type': 'string', 'index': 'not_analyzed'},
        'target_provision_state': {'type': 'string', 'index': 'not_analyzed'},
        'provision_updated_at': {'type': 'date'},
        'maintenance': {'type': 'boolean'},
        'maintenance_reason': {'type': 'string'},
        'console_enabled': {'type': 'boolean'},
        'last_error': {'type': 'string'},
        'resource_class': {'type': 'string', 'index': 'not_analyzed'},
        'inspection_started_at': {'type': 'date'},
        'inspection_finished_at': {'type': 'date'},
        'extra': {'type': 'object', 'dynamic': True, 'properties': {}},
        'network_interface': {'type': 'string', 'index': 'not_analyzed'},
        'created_at': {'type': 'date'},
        'updated_at': {'type': 'date'}
    }
}

PORT_MAPPING = {
    'dynamic': False,
    'properties': {
        # "id" field does not present in ironic API resource, this is
        # copy of "uuid"
        'id': {'type': 'string', 'index': 'not_analyzed'},
        'uuid': {'type': 'string', 'index': 'not_analyzed'},
        # "name" field does not present in ironic API resource, this is a
        # copy of "uuid"
        'name': {
            'type': 'string',
            'fields': {
                'raw': {'type': 'string', 'index': 'not_analyzed'}
            }
        },
        'node_uuid': {'type': 'string', 'index': 'not_analyzed'},
        'address': {'type': 'string', 'index': 'not_analyzed'},
        'extra': {'type': 'object', 'dynamic': True, 'properties': {}},
        'local_link_connection': {
            'type': 'object',
            'properties': {
                'switch_id': {'type': 'string', 'index': 'not_analyzed'},
                'port_id': {'type': 'string', 'index': 'not_analyzed'},
                'switch_info': {'type': 'string', 'index': 'not_analyzed'}
            }
        },
        'pxe_enabled': {'type': 'boolean'},
        'created_at': {'type': 'date'},
        'updated_at': {'type': 'date'}
    }
}

CHASSIS_MAPPING = {
    'dynamic': False,
    'properties': {
        # "id" field does not present in ironic API resource, this is a
        # copy of "uuid"
        'id': {'type': 'string', 'index': 'not_analyzed'},
        'uuid': {'type': 'string', 'index': 'not_analyzed'},
        # "name" field does not present in ironic API resource, this is a
        # copy of "uuid"
        'name': {
            'type': 'string',
            'fields': {
                'raw': {'type': 'string', 'index': 'not_analyzed'}
            }
        },
        'extra': {'type': 'object', 'dynamic': True, 'properties': {}},
        'description': {'type': 'string'},
        'created_at': {'type': 'date'},
        'updated_at': {'type': 'date'}
    }
}


NODE_FIELDS = NODE_MAPPING['properties'].keys()
PORT_FIELDS = PORT_MAPPING['properties'].keys()
CHASSIS_FIELDS = PORT_MAPPING['properties'].keys()
