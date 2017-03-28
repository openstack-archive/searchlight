# Copyright (c) 2016 Hewlett-Packard Development Company, L.P.
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

import logging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins import swift
from searchlight.elasticsearch.plugins.swift \
    import serialize_swift_account_notification
from searchlight.elasticsearch.plugins.swift \
    import serialize_swift_container_notification
from searchlight.elasticsearch.plugins.swift \
    import serialize_swift_object_notification
from searchlight import pipeline


LOG = logging.getLogger(__name__)


class SwiftAccountHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        super(SwiftAccountHandler, self).__init__(*args, **kwargs)

    @classmethod
    def _get_notification_exchanges(cls):
        return ['swift']

    def get_event_handlers(self):
        return {
            "account.create": self.create_or_update,
            "account.metadata": self.create_or_update,
            "account.delete": self.delete
        }

    def get_log_fields(self, event_type, payload):
        return ('account', payload.get('account')),

    def create_or_update(self, event_type, payload, timestamp):
        serialized_account = serialize_swift_account_notification(payload)
        try:
            self.index_helper.save_document(
                serialized_account,
                version=self.get_version(serialized_account, timestamp))
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
                                      serialized_account
                                      )
        except Exception as exc:
            LOG.error('Error saving account %(id)s '
                      'in index. Error: %(exc)s' %
                      {'id': payload['id'], 'exc': exc})

    def delete(self, event_type, payload, timestamp):
        version = self.get_version(payload, timestamp,
                                   preferred_date_field='deleted_at')
        id = payload['account']
        try:
            self.index_helper.delete_document(
                {'_id': id, '_version': version,
                 '_routing': payload['account']})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       id)
        except Exception as exc:
            LOG.error('Error deleting account %(id)s '
                      'from index. Error: %(exc)s' %
                      {'id': id, 'exc': exc})


class SwiftContainerHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        self.object_helper = kwargs.pop('object_helper')
        super(SwiftContainerHandler, self).__init__(*args, **kwargs)

    @classmethod
    def _get_notification_exchanges(cls):
        return ['swift']

    def get_event_handlers(self):
        return {
            "container.create": self.create_or_update,
            "container.metadata": self.create_or_update,
            "container.delete": self.delete
        }

    def get_log_fields(self, event_type, payload):
        return (
            ('account', payload.get('account')),
            ('container', payload.get('container'))
        )

    def create_or_update(self, event_type, payload, timestamp):
        serialized_payload = serialize_swift_container_notification(payload)
        try:
            self.index_helper.save_document(
                serialized_payload,
                version=self.get_version(serialized_payload, timestamp))
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
                                      serialized_payload)
        except Exception as exc:
            LOG.error('Error saving container %(id)s '
                      'in index. Error: %(exc)s' %
                      {'id': payload['id'], 'exc': exc})

    def delete(self, event_type, payload, timestamp):
        # notification payload doesn't have any date/time fields
        # so temporarily use metadata timestamp value as
        # updated_at field to retrieve version
        # Remove it when notification starts sending datetime field(s)
        payload['updated_at'] = timestamp
        version = self.get_version(payload, timestamp,
                                   preferred_date_field='deleted_at')
        del payload['updated_at']

        id = payload['account'] + swift.ID_SEP + payload['container']
        items = []
        try:
            delete_docs = self.object_helper.delete_documents_with_parent(
                id, version=version)
            items.extend(
                [pipeline.DeleteItem(
                    self.index_helper.plugin,
                    event_type,
                    payload,
                    doc['_id']) for doc in delete_docs])
        except Exception as exc:
            LOG.error('Error deleting objects in container %(id)s '
                      'from index. Error: %(exc)s' %
                      {'id': id, 'exc': exc})
        try:
            self.index_helper.delete_document(
                {'_id': id, '_version': version,
                 '_routing': payload['account']})
            items.append(
                pipeline.DeleteItem(
                    self.index_helper.plugin,
                    event_type,
                    payload,
                )
            )
            return items
        except Exception as exc:
            LOG.error('Error deleting container %(id)s '
                      'from index. Error: %(exc)s' %
                      {'id': id, 'exc': exc})


class SwiftObjectHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        super(SwiftObjectHandler, self).__init__(*args, **kwargs)

    @classmethod
    def _get_notification_exchanges(cls):
        return ['swift']

    def get_event_handlers(self):
        return {
            "object.create": self.create_or_update,
            "object.metadata": self.create_or_update,
            "object.delete": self.delete
        }

    def get_log_fields(self, event_type, payload):
        return (
            ('account', payload.get('account')),
            ('container', payload.get('container')),
            ('object', payload.get('object'))
        )

    def create_or_update(self, event_type, payload, timestamp):
        serialized_payload = serialize_swift_object_notification(payload)
        try:
            self.index_helper.save_document(
                serialized_payload,
                version=self.get_version(serialized_payload, timestamp)
            )
            return pipeline.IndexItem(
                self.index_helper.plugin,
                event_type,
                payload,
                serialized_payload
            )
        except Exception as exc:
            LOG.error('Error saving object %(id)s '
                      'in index. Error: %(exc)s' %
                      {'id': payload['id'], 'exc': exc})

    def delete(self, event_type, payload, timestamp):
        # notification payload doesn't have any date/time fields
        # so temporarily use metadata timestamp value as
        # updated_at field to retrieve version
        # Remove it when notification starts sending datetime field(s)
        payload['updated_at'] = timestamp
        version = self.get_version(payload, timestamp,
                                   preferred_date_field='deleted_at')
        del payload['updated_at']

        id = payload['account'] + swift.ID_SEP + \
            payload['container'] + swift.ID_SEP + \
            payload['object']
        try:
            self.index_helper.delete_document(
                {'_id': id, '_version': version,
                 '_routing': payload['account']})
            return pipeline.DeleteItem(
                self.index_helper.plugin,
                event_type,
                payload,
                id
            )
        except Exception as exc:
            LOG.error('Error deleting object %(id)s '
                      'from index. Error: %(exc)s' %
                      {'id': id, 'exc': exc})
