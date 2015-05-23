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

from oslo_config import cfg
from oslo_log import log as logging
# TODO: Figure this out better. The glance plugin uses the API policy module
# as the enforcer for property_utils
from oslo_policy import opts as oslo_policy_opts
import oslo_messaging
import stevedore

from searchlight import i18n
from searchlight.openstack.common import service as os_service

LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE


oslo_policy_opts._register(cfg.CONF)


class NotificationEndpoint(object):

    def __init__(self):
        self.plugins = get_plugins()
        self.notification_target_map = dict()
        for plugin in self.plugins:
            try:
                event_list = plugin.obj.get_notification_supported_events()
                for event in event_list:
                    LOG.debug("Registering event '%s' for plugin '%s'", event, plugin.name)
                    self.notification_target_map[event.lower()] = plugin.obj
            except Exception as e:
                LOG.error(_LE("Failed to retrieve supported notification"
                              " events from search plugins "
                              "%(ext)s: %(e)s") %
                          {'ext': plugin.name, 'e': e})

    def topics_and_exchanges(self):
        topics_exchanges = set()
        for plugin in self.plugins:
            for plugin_topic in plugin.get_notification_topic_exchanges():
                if isinstance(plugin_topic, basestring):
                    # TODO (sjmc7): Keep this in or not?
                    raise Exception(_LE("Plugin %s should return a list of" +
                        "topic exchange pairs", plugin.__class__.__name__))
                topics_exchanges.add(plugin_topics)

        return topics_exchanges

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        event_type_l = event_type.lower()
        if event_type_l in self.notification_target_map:
            plugin = self.notification_target_map[event_type_l]
            LOG.debug("Processing event '%s' with plugin '%s'", event_type_l, plugin.name)
            handler = plugin.get_notification_handler()
            handler.process(
                ctxt,
                publisher_id,
                event_type,
                payload,
                metadata)


class ListenerService(os_service.Service):
    def __init__(self, *args, **kwargs):
        super(ListenerService, self).__init__(*args, **kwargs)
        self.listeners = []

    def start(self):
        super(ListenerService, self).start()
        transport = oslo_messaging.get_transport(cfg.CONF)
        # TODO (sjmc7): This needs to come from the plugins, and from config
        # options rather than hardcoded. Refactor this out to a function
        # returning the set of topic,exchange pairs
        targets = [
            oslo_messaging.Target(topic="notifications", exchange="glance")
        ]
        endpoints = [
            NotificationEndpoint()
        ]
        listener = oslo_messaging.get_notification_listener(
            transport,
            targets,
            endpoints)
        listener.start()
        self.listeners.append(listener)

    def stop(self):
        for listener in self.listeners:
            listener.stop()
            listener.wait()
        super(ListenerService, self).stop()


def get_plugins():
    namespace = 'searchlight.index_backend'
    ext_manager = stevedore.extension.ExtensionManager(
        namespace, invoke_on_load=True)
    return ext_manager.extensions
