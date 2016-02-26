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

from oslo_log import log as logging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.neutron import serialize_network
from searchlight.elasticsearch.plugins.neutron import serialize_port
from searchlight import i18n

LOG = logging.getLogger(__name__)
_LW = i18n._LW
_LE = i18n._LE


class NetworkHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            # TODO(sjmc7): update? it seems only to support QoS updating
            'network.create.end': self.create_or_update,
            'network.delete.end': self.delete
        }

    def create_or_update(self, payload, timestamp):
        network_id = payload['network']['id']
        LOG.debug("Updating network information for %s", network_id)

        # Neutron doesn't give us any date/time information
        network = serialize_network(payload['network'], updated_at=timestamp)
        version = self.get_version(network, timestamp)

        self.index_helper.save_document(network, version=version)

    def delete(self, payload, timestamp):
        network_id = payload['network_id']
        LOG.debug("Deleting network information for %s", network_id)
        try:
            # Note that it's not necessary to delete ports; neutron will not
            # allow deletion of a network that has ports assigned on it
            self.index_helper.delete_document({'_id': network_id})
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting network %(network_id)s '
                'from index. Error: %(exc)s') %
                {'network_id': network_id, 'exc': exc})


class PortHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            'port.create.end': self.create_or_update,
            'port.update.end': self.create_or_update,
            'port.delete.end': self.delete
        }

    def create_or_update(self, payload, timestamp):
        port_id = payload['port']['id']
        LOG.debug("Updating port information for %s", port_id)

        # Version doesn't really make a huge amount of sense here but
        # is better than nothing
        port = serialize_port(payload['port'], updated_at=timestamp)
        version = self.get_version(port, timestamp)

        self.index_helper.save_document(port, version=version)

    def delete(self, payload, timestamp):
        port_id = payload['port_id']
        LOG.debug("Deleting port information for %s", port_id)
        try:
            self.index_helper.delete_document({'_id': port_id})
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting port %(port_id)s '
                'from index. Error: %(exc)s') %
                {'port_id': port_id, 'exc': exc})
