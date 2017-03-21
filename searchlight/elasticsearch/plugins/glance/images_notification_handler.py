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
from searchlight import pipeline

LOG = logging.getLogger(__name__)


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

    def get_log_fields(self, event_type, payload):
        return (
            ('id', payload.get('id')),
            ('owner', payload.get('owner'))
        )

    def serialize_notification(self, notification):
        return serialize_glance_notification(notification)

    def create_or_update(self, event_type, payload, timestamp):
        image_id = payload['id']
        try:
            image_payload = self.serialize_notification(payload)
            self.index_helper.save_document(
                image_payload,
                version=self.get_version(image_payload, timestamp))
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
                                      image_payload)
        except glanceclient.exc.NotFound:
            LOG.warning("Image %s not found; deleting" % image_id)
            return self.delete(event_type, payload, timestamp)

    def delete(self, event_type, payload, timestamp):
        image_id = payload['id']
        try:
            version = self.get_version(payload, timestamp,
                                       preferred_date_field='deleted_at')
            self.index_helper.delete_document(
                {'_id': image_id, '_version': version})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       image_id)
        except Exception as exc:
            LOG.error(
                'Error deleting image %(image_id)s from index: %(exc)s' %
                {'image_id': image_id, 'exc': exc})

    def sync_members(self, event_type, payload, timestamp):
        image_id = payload['image_id']
        image_es = self.index_helper.get_document(image_id,
                                                  for_admin=True)

        image_payload = serialize_glance_image_members(image_es['_source'],
                                                       payload)

        self.index_helper.save_document(image_payload)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  image_payload)
