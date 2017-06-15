# Copyright 2016 Intel Corporation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_log import log as logging
from searchlight.elasticsearch.plugins.utils import normalize_es_document
import stevedore

LOG = logging.getLogger(__name__)


class Pipeline(object):

    def __init__(self, plugin, publisher):
        self.plugin = plugin
        self.publisher = publisher
        self.notification_handler = self.plugin.get_notification_handler()

    def supported_events(self):
        if self.notification_handler:
            return self.notification_handler.\
                get_notification_supported_events()
        return []


class PipelineManager(object):

    def __init__(self, plugins):
        self.pipelines = []
        for plugin in plugins.values():
            publishers = []
            if plugin.obj.publishers:
                for publisher_name in plugin.obj.publishers:
                    try:
                        publishers.append(get_publisher(publisher_name))
                    except Exception as exc:
                        LOG.warning(
                            'Unable to load publisher %(publisher)s '
                            'of plugin %(plugin)s: %(exc)s' % {
                                'publisher': publisher_name,
                                'plugin': plugin.obj.name,
                                'exc': exc}
                        )

            for publisher in publishers:
                pipeline = Pipeline(plugin.obj, publisher)
                self.pipelines.append(pipeline)

    def publish(self, items):
        for pipeline in self.pipelines:
            for item in items:
                if item.event_type in pipeline.supported_events():
                    pipeline.publisher.publish(item)


class PipelineItem(object):
    """
    Base class to store notification and resource info
    """

    def __init__(self, plugin, event_type, payload):
        """
        :param plugin: Plugin instance of modified resource.
        :param event_type: event type of the notification.
        :param payload: notification payload received. Note that payload may
        contain sensitive information shouldn't be passed on.
        """
        self.plugin = plugin
        self.resource_type = plugin.get_document_type()
        self.payload = payload
        self.event_type = event_type


class IndexItem(PipelineItem):

    def __init__(self, plugin, event_type, payload, doc):
        """
        :param plugin: Plugin instance of modified resource.
        :param event_type: event type of the notification.
        :param payload: notification payload received. Note that payload may
        contain sensitive information shouldn't be passed on.
        :param doc: resource document passed to publishers.
        """
        super(IndexItem, self).__init__(plugin, event_type, payload)
        self.doc_id = doc[plugin.get_document_id_field()]
        self.doc = normalize_es_document(doc, plugin)


class DeleteItem(PipelineItem):

    def __init__(self, resource_type, event_type, payload, doc_id):
        """
        :param resource_type: Heat resource type of modified resources,
        see searchlight/common/resource_types.py for more detail.
        :param event_type: event type of the notification.
        :param payload: notification payload received, Note that payload may
        contain sensitive information shouldn't be passed on.
        :param doc_id: id of document to be deleted.
        """
        super(DeleteItem, self).__init__(resource_type, event_type, payload)
        self.doc_id = doc_id


def get_publisher(url):
    namespace = 'searchlight.publisher'
    loaded_driver = stevedore.driver.DriverManager(
        namespace, url, invoke_on_load=True)
    return loaded_driver.driver
