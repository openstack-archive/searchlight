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

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins import designate
from searchlight.elasticsearch.plugins.designate import notification_handlers


class RecordSetIndex(base.IndexBase):
    def get_index_name(self):
        return "searchlight"

    def get_document_type(self):
        return "OS::Designate::RecordSet"

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
                "records": {
                    "type": "nested",
                    "properties": {
                        "data": {"type": "string"}
                    }
                },
            },
            "_parent": {
                "type": "OS::Designate::Zone"
            }
        }

    def _get_rbac_field_filters(self, request_context):
        return [
            {"term": {"project_id": request_context.owner}}
        ]

    def get_objects(self):
        from searchlight.elasticsearch.plugins import openstack_clients
        client = openstack_clients.get_designateclient()

        zones = designate._walk_pages(
            client.zones.list, {"all_tenants": str(True)}, limit=50)

        for zone in zones:
            recordsets = designate._get_recordsets(zone['id'])
            for rs in recordsets:
                rs['project_id'] = zone['project_id']
                yield rs

    def get_parent_id_field(self):
        return 'zone_id'

    def serialize(self, obj):
        obj["_parent"] = obj["zone_id"]
        return designate._serialize_recordset(obj)

    def get_notification_handler(self):
        return notification_handlers.RecordSetHandler(
            self.engine,
            self.get_index_name(),
            self.get_document_type()
        )

    # TODO(sjmc7): These functions really belong to the notification handler,
    # not this class
    def get_notification_topics_exchanges(self):
        # TODO(sjmc7): More importantly, this should come from config
        return set([('searchlight_indexer', 'designate')])

    def get_notification_supported_events(self):
        return [
            "dns.recordset.create",
            "dns.recordset.update",
            "dns.recordset.delete"]
