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
from searchlight.elasticsearch.plugins.cinder import serialize_cinder_volume
from searchlight import pipeline


LOG = logging.getLogger(__name__)


class VolumeHandler(base.NotificationBase):
    """Handles cinder volume notifications. These can come as a result of
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
            'volume.update.end': self.create_or_update,
            'volume.create.end': self.create_or_update,
            'volume.delete.end': self.delete,
            # TODO(sjmc7) These could be implemented as scripted updates
            'volume.attach.end': self.create_or_update,
            'volume.detach.end': self.create_or_update,
            'volume.retype': self.create_or_update,
        }

    def get_log_fields(self, event_type, payload):
        return ('id', payload.get('volume_id')),

    def create_or_update(self, event_type, payload, timestamp):
        volume_id = payload['volume_id']
        LOG.debug("Updating cinder volume information for %s", volume_id)

        try:
            volume_payload = serialize_cinder_volume(volume_id)
            version = self.get_version(volume_payload, timestamp)
            self.index_helper.save_document(volume_payload, version=version)
            return pipeline.IndexItem(
                self.index_helper.plugin,
                event_type,
                payload,
                volume_payload
            )
        except cinderclient.exceptions.NotFound:
            LOG.warning("Volume %s not found; deleting" % volume_id)
            self.delete(payload, timestamp)

    def delete(self, event_type, payload, timestamp):
        volume_id = payload['volume_id']
        LOG.debug("Deleting cinder volume information for %s", volume_id)
        if not volume_id:
            return

        try:
            self.index_helper.delete_document({'_id': volume_id})
            return pipeline.DeleteItem(
                self.index_helper.plugin,
                event_type,
                payload,
                volume_id
            )
        except Exception as exc:
            LOG.error(
                'Error deleting volume %(volume_id)s '
                'from index. Error: %(exc)s' %
                {'volume_id': volume_id, 'exc': exc})
