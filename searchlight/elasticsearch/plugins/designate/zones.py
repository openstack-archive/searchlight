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


class ZoneIndex(base.IndexBase):
    def get_index_name(self):
        return "searchlight"

    def get_document_type(self):
        return "OS::Designate::Zone"

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
        }

    def _get_rbac_field_filters(self, request_context):
        return [
            {"term": {"project_id": request_context.owner}}
        ]

    def get_objects(self):
        from searchlight.elasticsearch.plugins import openstack_clients
        client = openstack_clients.get_designateclient()

        iterator = designate._walk_pages(
            client.zones.list,
            {"all_tenants": str(True)}, limit=50)
        for zone in iterator:
            yield zone

    def serialize(self, obj):
        obj.pop("links")
        return obj

    def get_notification_handler(self):
        return notification_handlers.DomainHandler(
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
            "dns.domain.create",
            "dns.domain.update",
            "dns.domain.delete",
            "dns.domain.exists"]
