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
from oslo_log import log as logging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins import designate
from searchlight import pipeline


LOG = logging.getLogger(__name__)


class ZoneHandler(base.NotificationBase):
    def __init__(self, *args, **kwargs):
        self.recordset_helper = kwargs.pop('recordset_helper')
        super(ZoneHandler, self).__init__(*args, **kwargs)
        self.domain_delete_keys = ['deleted_at', 'deleted',
                                   'attributes', 'recordsets']

    @classmethod
    def _get_notification_exchanges(cls):
        return ['designate']

    def get_event_handlers(self):

        # domain(v1) and zone(v2) are same except for the name.
        # To keep it backward compatible, designate sends two sets of
        # notification events (dns.zone.xxxx and dns.domain.xxxx) for
        # every domain or zone action within v1 or v2 api.
        # So we ignore all dns.domain.xxxx events.
        return {
            "dns.zone.create": self.create_or_update,
            "dns.zone.update": self.create_or_update,
            "dns.zone.delete": self.delete
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
        if (event_type == 'dns.zone.update' and
                payload.get('status') == 'DELETED'):
            LOG.debug("Ignoring update notification for Domain with DELETED "
                      "status; event will be processed on delete event")
            return None

        items = super(ZoneHandler, self).process(
            ctxt, publisher_id, event_type, payload, metadata)
        try:
            # NOTE: So if this is an initial zone we need to index the SOA / NS
            # records it will have. Let's do this when receiving the create
            # event.
            if event_type == 'dns.zone.create':
                if not items:
                    LOG.warning("Not writing initial recordsets; exception "
                                "occurred during zone indexing")
                    return None

                recordsets = designate._get_recordsets(payload['id'])
                serialized_recordsets = []
                recordset_versions = []
                for rs in recordsets:
                    rs = designate._serialize_recordset(rs)

                    # So project ID isn't provided in the recordset api.
                    rs['project_id'] = payload['project_id']

                    serialized_recordsets.append(rs)

                    # Use the timestamp from *this* notification but the
                    # updated_at from each recordset (which empirically appears
                    # to be the same for all initial recordsets)
                    recordset_versions.append(
                        self.get_version(rs, metadata['timestamp']))
                    items.append(
                        pipeline.IndexItem(self.recordset_helper.plugin,
                                           event_type,
                                           payload,
                                           rs
                                           )
                    )
                self.recordset_helper.save_documents(
                    serialized_recordsets, versions=recordset_versions)
                return items
        except Exception as e:
            LOG.exception(e)

    def create_or_update(self, event_type, payload, timestamp):
        zone_payload = self._serialize(payload)
        self.index_helper.save_document(
            zone_payload,
            version=self.get_version(zone_payload, timestamp))
        return pipeline.IndexItem(
            self.index_helper.plugin,
            event_type,
            payload,
            zone_payload)

    def delete(self, event_type, payload, timestamp):
        zone_id = payload['id']
        version = self.get_version(payload, timestamp,
                                   preferred_date_field='deleted_at')
        delete_recordset = self.recordset_helper.delete_documents_with_parent(
            zone_id,
            version=version)
        items = [pipeline.DeleteItem(
            self.recordset_helper.plugin,
            event_type,
            payload,
            rs['_id']) for rs in delete_recordset]

        try:
            self.index_helper.delete_document(
                {'_id': zone_id, '_version': version})
            items.append(pipeline.DeleteItem(self.index_helper.plugin,
                                             event_type,
                                             payload,
                                             zone_id))
        except exceptions.NotFoundError:
            msg = "Zone %s not found when deleting"
            LOG.error(msg, zone_id)
        return items


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
            "dns.recordset.create": self.create_or_update_recordset,
            "dns.recordset.update": self.create_or_update_recordset,
            "dns.recordset.delete": self.delete_recordset,
        }

    def get_log_fields(self, event_type, payload):
        return (
            ('id', payload.get('id')),
            ('zone_id', payload.get('zone_id'))
        )

    def create_or_update_recordset(self, event_type, payload, timestamp):
        rs_payload = self._serialize(payload)
        self.index_helper.save_document(
            rs_payload,
            version=self.get_version(rs_payload, timestamp))
        return pipeline.IndexItem(
            self.index_helper.plugin,
            event_type,
            payload,
            rs_payload)

    def _serialize(self, obj):
        obj['project_id'] = obj.pop('tenant_id')
        obj['records'] = [i['data'] for i in obj['records']]
        if not obj['updated_at'] and obj['created_at']:
            obj['updated_at'] = obj['created_at']
        return obj

    def delete_recordset(self, event_type, payload, timestamp):
        version = self.get_version(payload, timestamp,
                                   preferred_date_field='deleted_at')
        self.index_helper.delete_document(
            {'_id': payload['id'], '_version': version,
             '_parent': payload['zone_id']})
        return pipeline.DeleteItem(self.index_helper.plugin,
                                   event_type,
                                   payload,
                                   payload['id'])
