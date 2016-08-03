# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from searchlight.common import resource_types
from searchlight.elasticsearch.plugins import designate
from searchlight.elasticsearch.plugins.designate import notification_handlers


class ZoneIndex(designate.DesignateBase):
    NotificationHandlerCls = notification_handlers.ZoneHandler

    def get_notification_handler(self):
        """Override because the zone handler needs a handle to recordset
        indexer (for initial recordset indexing).
        """
        return self.NotificationHandlerCls(
            self.index_helper,
            self.options,
            recordset_helper=self.child_plugins[0].index_helper)

    @classmethod
    def get_document_type(cls):
        return resource_types.DESIGNATE_ZONE

    def get_mapping(self):
        return {
            "dynamic": True,
            "dynamic_templates": [
                {
                    "_id": {
                        "match": "*_id",
                        "match_mapping_type": "string",
                        "mapping": {
                            "type": "string",
                            "index": "not_analyzed"
                        }
                    }
                }
            ],
            "properties": {
                "id": {"type": "string", "index": "not_analyzed"},
                "project_id": {"type": "string", "index": "not_analyzed"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "name": {
                    "type": "string",
                    "fields": {
                        "raw": {"type": "string", "index": "not_analyzed"}
                    }
                },
                "description": {"type": "string"},
                "version": {"type": "integer"},
                "shard": {"type": "integer"},
                "email": {"type": "string"},
                "ttl": {"type": "integer"},
                "refresh": {"type": "integer"},
                "retry": {"type": "integer"},
                "expire": {"type": "integer"},
                "minimum": {"type": "integer"},
                "serial": {"type": "integer"},
                "status": {"type": "string", "index": "not_analyzed"},
                "action": {"type": "string", "index": "not_analyzed"},
                "type": {"type": "string", "index": "not_analyzed"},
                "transferred_at": {"type": "string"},
                "masters": {"type": "string"}
            },
            "_meta": {
                "project_id": {
                    "resource_type": resource_types.KEYSTONE_PROJECT
                }
            }
        }

    @property
    def facets_with_options(self):
        return ('status', 'type')

    @property
    def facets_excluded(self):
        """Facets either not available or available only to admins"""
        return {'project_id': True}

    @property
    def resource_allowed_policy_target(self):
        return 'get_zones'

    @property
    def service_type(self):
        return 'dns'

    def _get_rbac_field_filters(self, request_context):
        return [
            {"term": {"project_id": request_context.owner}}
        ]

    def get_objects(self):
        for zone in designate._get_zones():
            yield zone

    def serialize(self, obj):
        obj.pop("links", None)
        if not obj['updated_at'] and obj['created_at']:
            obj['updated_at'] = obj['created_at']
        if 'project_id' not in obj:
            obj['project_id'] = obj['tenant_id']
        return obj
