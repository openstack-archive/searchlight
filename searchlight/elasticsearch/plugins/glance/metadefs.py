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

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.glance \
    import metadefs_notification_handler
from searchlight.elasticsearch.plugins.glance \
    import serialize_glance_metadef_ns


class MetadefIndex(base.IndexBase):
    def __init__(self):
        super(MetadefIndex, self).__init__()

    def get_index_name(self):
        return 'searchlight'

    def get_document_type(self):
        return 'OS::Glance::Metadef'

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
            '_id': {
                'path': 'namespace',
            },
            'properties': {
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'},
                'display_name': {'type': 'string'},
                'description': {'type': 'string'},
                'namespace': {'type': 'string', 'index': 'not_analyzed'},
                'owner': {'type': 'string', 'index': 'not_analyzed'},
                'visibility': {'type': 'string', 'index': 'not_analyzed'},
                'resource_types': {
                    'type': 'nested',
                    'properties': {
                        'name': {'type': 'string'},
                        # TODO(sjmc7): add these back in? They don't seem
                        # to be accessible via the API
                        # 'prefix': {'type': 'string'},
                        # 'properties_target': {'type': 'string'},
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
                'tags': {
                    'type': 'nested',
                    'properties': {
                        'name': {'type': 'string'},
                    }
                }
            },
        }
        return mapping

    def _get_rbac_field_filters(self, request_context):
        return [
            {
                'or': [
                    {
                        'term': {
                            'owner': request_context.owner
                        }
                    },
                    {
                        'term': {
                            'visibility': 'public'
                        }
                    }
                ]
            }
        ]

    def get_objects(self):
        from searchlight.elasticsearch.plugins import openstack_clients
        gc = openstack_clients.get_glanceclient()
        return list(gc.metadefs_namespace.list())

    def serialize(self, metadef_obj):
        return serialize_glance_metadef_ns(metadef_obj)

    def get_notification_handler(self):
        return metadefs_notification_handler.MetadefHandler(
            self.engine,
            self.get_index_name(),
            self.get_document_type()
        )

    def get_notification_topics_exchanges(self):
        return set([('searchlight_indexer', 'glance')])

    def get_notification_supported_events(self):
        return [
            "metadef_namespace.create",
            "metadef_namespace.update",
            "metadef_namespace.delete",
            "metadef_object.create",
            "metadef_object.update",
            "metadef_object.delete",
            "metadef_property.create",
            "metadef_property.update",
            "metadef_property.delete",
            "metadef_tag.create",
            "metadef_tag.update",
            "metadef_tag.delete",
            "metadef_resource_type.create",
            "metadef_resource_type.delete",
            "metadef_namespace.delete_properties",
            "metadef_namespace.delete_objects",
            "metadef_namespace.delete_tags"
        ]
