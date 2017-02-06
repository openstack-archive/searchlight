# Copyright 2015 Intel Corporation
# All Rights Reserved.
#
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

from searchlight.common import resource_types
from searchlight.common import utils
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.glance \
    import metadefs_notification_handler
from searchlight.elasticsearch.plugins.glance \
    import serialize_glance_metadef_ns


class MetadefIndex(base.IndexBase):
    NotificationHandlerCls = metadefs_notification_handler.MetadefHandler

    @classmethod
    def get_document_type(cls):
        return resource_types.GLANCE_METADEF

    def get_document_id_field(self):
        return 'namespace'

    def get_mapping(self):
        property_mapping = {
            'dynamic': True,
            'type': 'nested',
            'properties': {
                'name': {'type': 'string', 'index': 'not_analyzed'},
                'type': {'type': 'string'},
                'title': {'type': 'string'},
                'description': {'type': 'string'},
            }
        }
        mapping = {
            'properties': {
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'},
                'display_name': {'type': 'string'},
                'description': {'type': 'string'},
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'namespace': {'type': 'string', 'index': 'not_analyzed'},
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'owner': {'type': 'string', 'index': 'not_analyzed'},
                'project_id': {'type': 'string', 'index': 'not_analyzed'},
                'visibility': {'type': 'string', 'index': 'not_analyzed'},
                'resource_types': {
                    'type': 'object',
                    'properties': {
                        # sjmc7 - removing prefix, properties_target since they
                        # aren't accessible though the API
                        'name': {'type': 'string'}
                    },
                },
                'objects': {
                    'type': 'nested',
                    'properties': {
                        'id': {'type': 'string', 'index': 'not_analyzed'},
                        'name': {'type': 'string'},
                        'description': {'type': 'string'},
                        'properties': property_mapping,
                    }
                },
                'properties': property_mapping,
                'tags': {'type': 'string'}
            },
            "_meta": {
                "owner": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                },
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                }
            }

        }
        return mapping

    @property
    def resource_allowed_policy_target(self):
        return 'get_metadef_namespaces'

    @property
    def service_type(self):
        return 'image'

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'owner': request_context.owner}},
            {'term': {'visibility': 'public'}}
        ]

    def get_objects(self):
        from searchlight.elasticsearch.plugins import openstack_clients
        gc = openstack_clients.get_glanceclient()
        return list(gc.metadefs_namespace.list())

    def serialize(self, metadef_obj):
        return serialize_glance_metadef_ns(metadef_obj)

    def filter_result(self, hit, request_context):
        super(MetadefIndex, self).filter_result(hit, request_context)

        # Revert the change we make to fit the 'tags' mapping used in other
        # plugins (see serialize_glance_metadef_ns in __init__.py)
        highlight = hit.get('highlight')
        if highlight:
            utils.restore_dots_in_field_names(highlight)
        source = hit['_source']
        utils.restore_dots_in_field_names(source)
        tags = source.pop('tags', None)
        if tags is not None:
            source['tags'] = [{"name": tag} for tag in tags]
