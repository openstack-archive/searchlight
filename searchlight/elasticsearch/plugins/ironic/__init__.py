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

import functools


def serialize_resource(resource, fields):
    # NOTE: not all fields present in some notifications, we should not reset
    # them
    serialized = {field: resource[field] for field in fields
                  if field in resource}
    # Clone uuid
    serialized['id'] = resource['uuid']
    if not serialized['updated_at']:
        serialized['updated_at'] = resource['created_at']
    # "name" field is mandatory
    if not serialized.get('name'):
        serialized['name'] = resource['uuid']
    # Remap node "properties" field
    if 'properties' in resource:
        serialized['node_properties'] = resource['properties']

    return serialized


def obj_payload(payload):
    return payload['ironic_object.data']


def versioned_payload(func):
    @functools.wraps(func)
    def wrapper(self, event_type, payload, timestamp):
        return func(self, event_type, obj_payload(payload), timestamp)
    return wrapper
