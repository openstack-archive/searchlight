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

from elasticsearch import exceptions
from elasticsearch import helpers
from oslo_log import log as logging
import oslo_messaging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins import designate
from searchlight import i18n


LOG = logging.getLogger(__name__)
_LW = i18n._LW


class DomainHandler(base.NotificationBase):
    def __init__(self, *args, **kwargs):
        super(DomainHandler, self).__init__(*args, **kwargs)
        self.domain_delete_keys = ['deleted_at', 'deleted',
                                   'attributes', 'recordsets']

    @classmethod
    def _get_notification_exchanges(cls):
        return ['designate']

    def get_event_handlers(self):
        return {
            "dns.domain.create": self.create_or_update,
            "dns.domain.update": self.create_or_update,
            "dns.domain.delete": self.delete,
            "dns.domain.exists": self.create_or_update
        }

    def _serialize(self, payload):
        for key in self.domain_delete_keys:
            if key in payload:
                del payload[key]

        if 'masters' in payload:
            payload['masters'] = ["%(host)s:%(port)s" for i in
                                  payload["masters"]]
        payload['project_id'] = payload.pop('tenant_id')
        if not payload['updated_at'] and payload['created_at']:
            payload['updated_at'] = payload['created_at']

        return payload

    def process(self, ctxt, publisher_id, event_type, payload, metadata):
        handled = super(DomainHandler, self).process(
            ctxt, publisher_id, event_type, payload, metadata)
        try:
            # NOTE: So if this is a initial zone we need to index the SOA / NS
            # records it will have. Let's do this when recieving the create
            # event.
            if event_type == 'dns.domain.create':
                if handled != oslo_messaging.NotificationResult.HANDLED:
                    LOG.warning(_LW("Not writing initial recordsets; exception"
                                    "occurred during domain indexing"))
                    return None

                recordsets = designate._get_recordsets(payload['id'])
                for rs in recordsets:
                    rs = designate._serialize_recordset(rs)

                    # So project ID isn't provided in the recordset api.
                    rs['project_id'] = payload['project_id']

                    # TODO(ekarlso,sjmc7): doc_type below should come from
                    # the recordset plugin
                    # registers options
                    self.engine.index(
                        index=self.index_name,
                        doc_type=RecordSetHandler.DOCUMENT_TYPE,
                        body=rs,
                        parent=rs["zone_id"],
                        id=rs["id"])
            return oslo_messaging.NotificationResult.HANDLED
        except Exception as e:
            LOG.exception(e)

    def create_or_update(self, payload):
        payload = self._serialize(payload)
        self.index_helper.save_document(payload)

    def delete(self, payload):
        zone_id = payload['id']

        query = {
            'fields': 'id',
            'query': {
                'term': {
                    'zone_id': zone_id
                }
            }
        }

        documents = helpers.scan(
            client=self.index_helper.engine,
            index=self.index_name,
            doc_type=self.document_type,
            query=query)

        # TODO(sjmc7) The code below will still work because DNS zones aren't
        # split by role. If they ever ARE, it will stop working, since the
        # ids won't match up (_ADMIN, _USER)
        actions = []
        for document in documents:
            action = {
                '_id': document['_id'],
                '_op_type': 'delete',
                '_index': self.index_name,
                '_type': self.document_type,
                '_parent': zone_id
            }
            actions.append(action)

        if actions:
            helpers.bulk(
                client=self.index_helper.engine,
                actions=actions)

        try:
            self.index_helper.delete_document_by_id(zone_id)
        except exceptions.NotFoundError:
            msg = "Zone %s not found when deleting"
            LOG.error(msg, zone_id)


class RecordSetHandler(base.NotificationBase):
    # TODO(sjmc7): see note above
    DOCUMENT_TYPE = "OS::Designate::RecordSet"

    def __init__(self, *args, **kwargs):
        super(RecordSetHandler, self).__init__(*args, **kwargs)
        self.record_delete_keys = ['deleted_at', 'deleted',
                                   'attributes']

    @classmethod
    def _get_notification_exchanges(cls):
        return ['designate']

    def get_event_handlers(self):
        return {
            "dns.recordset.create": self.create_or_update,
            "dns.recordset.update": self.create_or_update,
            "dns.recordset.delete": self.delete
        }

    def create_or_update(self, payload):
        payload = self._serialize(payload)
        self.index_helper.save_document(payload)

    def _serialize(self, obj):
        obj['project_id'] = obj.pop('tenant_id')
        obj['zone_id'] = obj.pop('domain_id')
        obj['records'] = [{"data": i["data"]} for i in obj["records"]]
        if not obj['updated_at'] and obj['created_at']:
            obj['updated_at'] = obj['created_at']
        return obj

    def delete(self, payload):
        self.index_helper.delete_document_by_id(payload['id'])
