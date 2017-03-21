# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import cinderclient.exceptions
from oslo_log import log as logging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.cinder import serialize_cinder_snapshot
from searchlight import pipeline

LOG = logging.getLogger(__name__)


class SnapshotHandler(base.NotificationBase):
    """Handles cinder snapshot notifications. These can come as a result of
    a user action (like a create, delete, metadata edit etc) or as a result of
    periodic auditing notifications cinder sends
    """

    @classmethod
    def _get_notification_exchanges(cls):
        # Unlike most services cinder doesn't override the exchange name from
        # the oslo.messaging default
        return ['openstack']

    def get_event_handlers(self):
        return {
            'snapshot.update.end': self.create_or_update,
            'snapshot.create.end': self.create_or_update,
            'snapshot.delete.end': self.delete,
        }

    def get_log_fields(self, event_type, payload):
        return (
            ('id', payload.get('snapshot_id')),
            ('volume_id', payload.get('volume_id'))
        )

    def create_or_update(self, event_type, payload, timestamp):
        snapshot_id = payload['snapshot_id']
        LOG.debug("Updating cinder snapshot information for %s", snapshot_id)
        try:
            snapshot_payload = serialize_cinder_snapshot(snapshot_id)
            version = self.get_version(snapshot_payload, timestamp)
            self.index_helper.save_document(snapshot_payload, version=version)
            return pipeline.IndexItem(
                self.index_helper.plugin,
                event_type,
                payload,
                snapshot_payload)
        except cinderclient.exceptions.NotFound:
            LOG.warning("Snapshot %s not found; deleting" % snapshot_id)
            self.delete(payload, timestamp)

    def delete(self, event_type, payload, timestamp):
        snapshot_id = payload['snapshot_id']
        volume_id = payload['volume_id']
        LOG.debug("Deleting cinder snapshot information for %s", snapshot_id)
        if not snapshot_id:
            return

        try:
            self.index_helper.delete_document({'_id': snapshot_id,
                                               '_parent': volume_id})
            return pipeline.DeleteItem(
                self.index_helper.plugin, event_type, payload, snapshot_id)
        except Exception as exc:
            LOG.error(
                'Error deleting snapshot %(snapshot_id)s '
                'from index. Error: %(exc)s' %
                {'snapshot_id': snapshot_id, 'exc': exc})
