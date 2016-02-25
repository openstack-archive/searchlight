# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

import glanceclient.exc
from oslo_log import log as logging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.glance \
    import serialize_glance_image_members
from searchlight.elasticsearch.plugins.glance \
    import serialize_glance_notification
from searchlight import i18n


LOG = logging.getLogger(__name__)
_LW = i18n._LW
_LE = i18n._LE


class ImageHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        super(ImageHandler, self).__init__(*args, **kwargs)
        self.image_delete_keys = ['deleted_at', 'deleted',
                                  'is_public', 'properties']

    @classmethod
    def _get_notification_exchanges(cls):
        return ['glance']

    def get_event_handlers(self):
        return {
            "image.create": self.create_or_update,
            "image.update": self.create_or_update,
            "image.delete": self.delete,
            "image.member.create": self.sync_members,
            "image.member.update": self.sync_members,
            "image.member.delete": self.sync_members
        }

    def serialize_notification(self, notification):
        return serialize_glance_notification(notification)

    def create_or_update(self, payload, timestamp):
        image_id = payload['id']
        try:
            payload = self.serialize_notification(payload)
            self.index_helper.save_document(
                payload,
                version=self.get_version(payload, timestamp))
        except glanceclient.exceptions.NotFound:
            LOG.warning(_LW("Image %s not found; deleting") % image_id)
            try:
                self.index_helper.delete_document_by_id(image_id)
            except Exception as exc:
                LOG.error(_LE(
                    'Error deleting image %(image_id)s from index: %(exc)s') %
                    {'image_id': image_id, 'exc': exc})

    def delete(self, payload, timestamp):
        image_id = payload['id']
        try:
            self.index_helper.delete_document_by_id(image_id)
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting image %(image_id)s from index: %(exc)s') %
                {'image_id': image_id, 'exc': exc})

    def sync_members(self, payload, timestamp):
        image_id = payload['image_id']
        image_es = self.index_helper.get_document(image_id,
                                                  for_admin=True)

        payload = serialize_glance_image_members(image_es['_source'], payload)

        self.index_helper.save_document(payload)
