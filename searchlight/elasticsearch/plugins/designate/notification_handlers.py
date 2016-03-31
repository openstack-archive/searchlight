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
import oslo_messaging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins import designate
from searchlight import i18n


LOG = logging.getLogger(__name__)
_LW = i18n._LW


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
            "dns.zone.delete": self.delete,
            "dns.zone.exists": self.create_or_update
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
            return oslo_messaging.NotificationResult.HANDLED

        handled = super(ZoneHandler, self).process(
            ctxt, publisher_id, event_type, payload, metadata)
        try:
            # NOTE: So if this is a initial zone we need to index the SOA / NS
            # records it will have. Let's do this when receiving the create
            # event.
            if event_type == 'dns.zone.create':
                if handled != oslo_messaging.NotificationResult.HANDLED:
                    LOG.warning(_LW("Not writing initial recordsets; exception"
                                    "occurred during zone indexing"))
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

                self.recordset_helper.save_documents(
                    serialized_recordsets, versions=recordset_versions)

            return oslo_messaging.NotificationResult.HANDLED
        except Exception as e:
            LOG.exception(e)

    def create_or_update(self, payload, timestamp):
        payload = self._serialize(payload)
        self.index_helper.save_document(
            payload,
            version=self.get_version(payload, timestamp))

    def delete(self, payload, timestamp):
        zone_id = payload['id']
        version = self.get_version(payload, timestamp)
        self.recordset_helper.delete_documents_with_parent(zone_id,
                                                           version=version)

        try:
            self.index_helper.delete_document(
                {'_id': zone_id, '_version': version})
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
            "dns.recordset.create": self.create_or_update_recordset,
            "dns.recordset.update": self.create_or_update_recordset,
            "dns.recordset.delete": self.delete_recordset,
            "dns.record.create": self.create_record,
            "dns.record.update": self.update_record,
            "dns.record.delete": self.delete_record
        }

    def create_or_update_recordset(self, payload, timestamp):

        # TODO(lakshmiS): Remove the check for empty records when v1 record
        # api is phased out
        # When using v1 create record api, designate sends dns.recordset.create
        # event with empty records so that subsequent dns.record.create
        # event can refer to the parent recordset_id. But the order of events
        # is not always right, so we ignore recordset when a recordset event
        # is created due to v1 record create event(we check for empty records
        # to associate it with v1 api. v2 recordset create event will never
        # have empty records).
        if payload['records']:
            payload = self._serialize(payload)
            self.index_helper.save_document(
                payload,
                version=self.get_version(payload, timestamp))
        else:
            LOG.debug("Ignoring recordset.create notification for empty"
                      "records; recordset will be created on "
                      "record.create event")

    def _serialize(self, obj):
        obj['project_id'] = obj.pop('tenant_id')
        obj['zone_id'] = obj.pop('zone_id')
        obj['records'] = [{"data": i["data"]} for i in obj["records"]]
        if not obj['updated_at'] and obj['created_at']:
            obj['updated_at'] = obj['created_at']
        return obj

    def delete_recordset(self, payload, timestamp):
        version = self.get_version(payload, timestamp)
        self.index_helper.delete_document(
            {'_id': payload['id'], '_version': version,
             '_parent': payload['zone_id']})

    # backward compatibility with v1 api
    # TODO(lakshmiS): Remove when designate v1 record api is phased out
    def create_record(self, payload, timestamp):
        version = self.get_version(payload, timestamp)

        # Sometimes dns.record.create event comes before dns.recordset.create
        # which can result in an recordset not found error.
        # Instead retrieve the whole recordset from api and save it, to avoid
        # race condition
        recordsets = designate._get_recordsets(payload['zone_id'])
        for recordset in recordsets:
            if recordset['id'] == payload['recordset_id']:
                payload = designate._serialize_recordset(recordset)
                self.index_helper.save_document(
                    payload, version=version)

    # backward compatibility with v1 api
    # TODO(lakshmiS): Remove when designate v1 record api is phased out
    def update_record(self, payload, timestamp):
        version = self.get_version(payload, timestamp)
        # designate v2 client doesn't support all_tenants param for
        # get recordset, so retrieve all recordsets for zone
        recordsets = designate._get_recordsets(payload['zone_id'])
        for recordset in recordsets:
            if recordset['id'] == payload['recordset_id']:
                payload = designate._serialize_recordset(recordset)
                # Since recordset doesn't have record id, there is no reliable
                # way to update a record as 'data' field itself can change.
                # update the recordset itself
                self.index_helper.save_document(
                    payload, version=version)

    # backward compatibility with v1 api
    # TODO(lakshmiS): Remove when designate v1 record api is phased out
    def delete_record(self, payload, timestamp):
        recordset_es = self.index_helper.get_document(
            payload['recordset_id'], for_admin=True,
            routing=payload['zone_id'])['_source']
        version = self.get_version(payload, timestamp)

        # designate v2 api output has only data field for record,
        # so there is no way to delete a record by record's id within
        # a recordset.
        recordset_es['records'] = filter(
            lambda record: record['data'] != payload['data'],
            recordset_es['records'])

        if recordset_es['records']:
            self.index_helper.save_document(
                recordset_es, version=version)
        else:
            self.index_helper.delete_document(
                {'_id': payload['recordset_id'], '_version': version,
                 '_parent': payload['zone_id']})
