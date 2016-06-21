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
from searchlight.elasticsearch.plugins.neutron import serialize_router
from searchlight.elasticsearch.plugins.neutron import serialize_subnet
from searchlight.elasticsearch.plugins import openstack_clients
from searchlight.elasticsearch.plugins import utils

from searchlight import i18n

LOG = logging.getLogger(__name__)
_LW = i18n._LW
_LE = i18n._LE
_LI = i18n._LI


class NetworkHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            'network.create.end': self.create_or_update,
            'network.update.end': self.create_or_update,
            'network.delete.end': self.delete
        }

    def create_or_update(self, payload, timestamp):
        network_id = payload['network']['id']
        LOG.debug("Updating network information for %s", network_id)

        # Neutron doesn't give us any date/time information
        network = serialize_network(payload['network'])
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
            'port.delete.end': self.delete,

            'router.interface.create': self.create_or_update_from_interface,
            'router.interface.delete': self.delete_from_interface
        }

    def create_or_update(self, payload, timestamp):
        port_id = payload['port']['id']

        if payload['port'].get('device_owner', None) == 'network:dhcp':
            # TODO(sjmc7): Remove this once we can get proper notifications
            # about DHCP ports.
            #  See https://bugs.launchpad.net/searchlight/+bug/1558790
            LOG.info(_LI("Skipping notification for DHCP port %s. If neutron "
                         "is sending notifications for DHCP ports, the "
                         "Searchlight plugin should be updated to process "
                         "them.") % port_id)
            return

        LOG.debug("Updating port information for %s", port_id)

        # Version doesn't really make a huge amount of sense here but
        # is better than nothing
        port = serialize_port(payload['port'])
        version = self.get_version(port, timestamp)

        self.index_helper.save_document(port, version=version)

    def delete(self, payload, timestamp):
        port_id = payload['port_id']
        LOG.debug("Deleting port information for %s; finding routing", port_id)
        try:
            self.index_helper.delete_document_unknown_parent(port_id)
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting port %(port_id)s '
                'from index. Error: %(exc)s') %
                {'port_id': port_id, 'exc': exc})

    def create_or_update_from_interface(self, payload, timestamp):
        """Unfortunately there seems to be no notification for ports created
        as part of a router interface creation, nor for DHCP ports. This
        means we need to go to the API.
        """
        port_id = payload['router_interface']['port_id']
        LOG.debug("Retrieving port %s from API", port_id)
        nc = openstack_clients.get_neutronclient()
        port = nc.show_port(port_id)['port']
        serialized = serialize_port(port)
        version = self.get_version(serialized, timestamp)
        self.index_helper.save_document(serialized, version=version)

    def delete_from_interface(self, payload, timestamp):
        """The partner of create_or_update_from_interface. There's no separate
        port deletion notification.
        """
        port_id = payload['router_interface']['port_id']
        LOG.debug("Deleting port %s from router interface", port_id)
        self.delete({'port_id': port_id}, timestamp)


class SubnetHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            'subnet.create.end': self.create_or_update,
            'subnet.update.end': self.create_or_update,
            'subnet.delete.end': self.delete
        }

    def create_or_update(self, payload, timestamp):
        subnet_id = payload['subnet']['id']
        LOG.debug("Updating subnet information for %s", subnet_id)
        subnet = serialize_subnet(payload['subnet'])

        version = self.get_version(subnet, timestamp)
        self.index_helper.save_document(subnet, version=version)

    def delete(self, payload, timestamp):
        subnet_id = payload['subnet_id']
        LOG.debug("Deleting subnet information for %s; finding routing",
                  subnet_id)
        try:
            self.index_helper.delete_document_unknown_parent(subnet_id)
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting subnet %(subnet_id)s '
                'from index: %(exc)s') %
                {'subnet_id': subnet_id, 'exc': exc})


class RouterHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            'router.create.end': self.create_or_update,
            'router.update.end': self.create_or_update,
            'router.delete.end': self.delete
        }

    def create_or_update(self, payload, timestamp):
        router_id = payload['router']['id']
        LOG.debug("Updating router information for %s", router_id)
        router = serialize_router(
            payload['router'],
            updated_at=utils.timestamp_to_isotime(timestamp))
        version = self.get_version(router, timestamp)
        self.index_helper.save_document(router, version=version)

    def delete(self, payload, timestamp):
        router_id = payload['router_id']
        LOG.debug("Deleting router information for %s", router_id)
        try:
            self.index_helper.delete_document({'_id': router_id})
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting router %(router)s '
                'from index: %(exc)s') %
                {'router': router_id, 'exc': exc})
