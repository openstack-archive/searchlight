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


class RecordSetIndex(designate.DesignateBase):
    NotificationHandlerCls = notification_handlers.RecordSetHandler

    @classmethod
    def parent_plugin_type(cls):
        return "OS::Designate::Zone"

    @classmethod
    def get_document_type(cls):
        return resource_types.DESIGNATE_RECORDSET

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
                "ttl": {"type": "integer"},
                "status": {"type": "string", "index": "not_analyzed"},
                "action": {"type": "string", "index": "not_analyzed"},
                "type": {"type": "string", "index": "not_analyzed"},
                "records": {"type": "string"},
                "zone_id": {"type": "string", "index": "not_analyzed"},
            },
            "_parent": {
                "type": self.parent_plugin_type()
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
        return 'get_recordsets'

    @property
    def service_type(self):
        return 'dns'

    def _get_rbac_field_filters(self, request_context):
        return [
            {"term": {"project_id": request_context.owner}}
        ]

    def get_objects(self):
        for zone in designate._get_zones():
            recordsets = designate._get_recordsets(zone['id'])
            for rs in recordsets:
                rs['project_id'] = zone['project_id']
                yield rs

    def get_parent_id_field(self):
        return 'zone_id'

    def serialize(self, obj):
        return designate._serialize_recordset(obj)
