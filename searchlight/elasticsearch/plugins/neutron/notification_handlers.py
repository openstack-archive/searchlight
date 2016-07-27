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
from searchlight.elasticsearch.plugins.neutron import serialize_floatingip
from searchlight.elasticsearch.plugins.neutron import serialize_network
from searchlight.elasticsearch.plugins.neutron import serialize_port
from searchlight.elasticsearch.plugins.neutron import serialize_router
from searchlight.elasticsearch.plugins.neutron import serialize_security_group
from searchlight.elasticsearch.plugins.neutron import serialize_subnet
from searchlight.elasticsearch.plugins import openstack_clients
from searchlight.elasticsearch.plugins import utils

import searchlight.elasticsearch
from searchlight.i18n import _LE, _LW, _LI

LOG = logging.getLogger(__name__)


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

    def get_log_fields(self, event_type, payload):
        # Delete and create/update notifications are different structures
        if 'network' in payload:
            return ('id', payload['network'].get('id')),
        elif 'network_id' in payload:
            return ('id', payload['network_id']),
        return ()

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

    def get_log_fields(self, event_type, payload):
        # Delete and create/update notifications are different structures, and
        # network_id will not be present for delete notifications
        if event_type.startswith('router.interface'):
            port_id = payload.get('router_interface', {}).get('port_id')
            network_id = payload.get('router_interface', {}).get('network_id')
        else:
            port_id = payload.get('port_id',
                                  payload.get('port', {}).get('id'))
            network_id = payload.get('port', {}).get('network_id')

        return (
            ('id', port_id),
            ('network_id', network_id)
        )

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

    def get_log_fields(self, event_type, payload):
        # Delete and create/update notifications are different structures, and
        # network_id will not be present for delete notifications
        subnet_id = payload.get('subnet_id',
                                payload.get('subnet', {}).get('id'))
        network_id = payload.get('subnet', {}).get('network_id')

        return (
            ('id', subnet_id),
            ('network_id', network_id)
        )

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

    def get_log_fields(self, event_type, payload):
        # Delete and create/update notifications are different structures
        router_id = payload.get('router_id',
                                payload.get('router', {}).get('id'))
        return ('id', router_id),

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


class FloatingIPHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            'floatingip.create.end': self.create_or_update,
            'floatingip.update.end': self.create_or_update,
            'floatingip.delete.end': self.delete
        }

    def get_log_fields(self, event_type, payload):
        # Delete and create/update notifications are different structures
        fip_id = payload.get('floatingip_id',
                             payload.get('floatingip', {}).get('id'))
        network_id = payload.get('floatingip', {}).get('floating_network_id')
        return (
            ('id', fip_id),
            ('network_id', network_id)
        )

    def create_or_update(self, payload, timestamp):
        fip_id = payload['floatingip']['id']
        LOG.debug("Updating floatingip information for %s", fip_id)
        floatingip = serialize_floatingip(
            payload['floatingip'],
            updated_at=utils.timestamp_to_isotime(timestamp))
        version = self.get_version(floatingip, timestamp)
        self.index_helper.save_document(floatingip, version=version)

    def delete(self, payload, timestamp):
        fip_id = payload['floatingip_id']
        LOG.debug("Deleting floatingip information for %s", fip_id)
        try:
            self.index_helper.delete_document({'_id': fip_id})
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting floating ip %(fip)s '
                'from index: %(exc)s') %
                {'fip': fip_id, 'exc': exc})


class SecurityGroupHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            'security_group.create.end': self.create_or_update_group,
            'security_group.delete.end': self.delete_group,
            'security_group_rule.create.end': self.create_or_update_rule,
            'security_group_rule.delete.end': self.delete_rule,
        }

    def get_log_fields(self, event_type, payload):
        if event_type == 'security_group_rule.create.end':
            sgr_payload = payload['security_group_rule']
            return (('id', sgr_payload['security_group_id']),
                    ('security_group_rule_id', sgr_payload['id']))
        elif event_type == 'security_group_rule.delete.end':
            return ('id', payload['security_group_rule_id']),

        group_id = payload.get('security_group_id',
                               payload.get('security_group', {}).get('id'))
        return ('id', group_id),

    def create_or_update_group(self, payload, timestamp):
        group_name = payload['security_group']['name']
        sec_id = payload['security_group']['id']
        LOG.debug("Updating security group information for %(grp)s (%(sec)s)" %
                  {'grp': group_name, 'sec': sec_id})

        # Version doesn't really make sense for security groups,
        # but we need to normalize the fields.
        doc = serialize_security_group(payload['security_group'])
        version = self.get_version(doc, timestamp)

        self.index_helper.save_document(doc, version=version)

    def delete_group(self, payload, timestamp):
        sec_id = payload['security_group_id']
        LOG.debug("Deleting security group information for %s", sec_id)
        try:
            self.index_helper.delete_document({'_id': sec_id})
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting security_group %(sec_id)s. Error: %(exc)s') %
                {'sec_id': sec_id, 'exc': exc})

    def create_or_update_rule(self, payload, timestamp):
        group_id = payload['security_group_rule']['security_group_id']
        LOG.debug("Updating security group rule information for %s", group_id)

        # Read, modify, write of an existing security group.
        doc = self.index_helper.get_document(group_id)

        if not doc:
            return
        body = doc['_source']
        if not body or 'security_group_rules' not in body:
            return

        body['security_group_rules'].append(payload['security_group_rule'])

        # Bump version for race condition prevention.
        version = doc['_version'] + 1
        self.index_helper.save_document(body, version=version)

    def delete_rule(self, payload, timestamp):
        rule_id = payload['security_group_rule_id']
        LOG.debug("Updating security group rule information for %s", rule_id)

        field = 'security_group_rules'

        # Read, modify, write of an existing security group.
        doc = self.get_doc_by_nested_field(
            "security_group_rules", "id", rule_id, version=True)

        if not doc:
            return
        body = doc['hits']['hits'][0]['_source']
        if not body or field not in body:
            return

        body[field] = list(filter(lambda r: r['id'] != rule_id, body[field]))

        # Bump version for race condition prevention.
        version = doc['hits']['hits'][0]['_version'] + 1
        self.index_helper.save_document(body, version=version)

    def get_doc_by_nested_field(self, path, field, value, version=False):
        """Query ElasticSearch based on a nested field. The caller will
           need to specify the path of the nested field as well as the
           field itself. We will include the 'version' field if commanded
           as such by the caller.
        """
        es_engine = searchlight.elasticsearch.get_api()

        # Set up query for accessing a nested field.
        nested_field = path + "." + field
        body = {"query": {"nested": {
                "path": path, "query": {"term": {nested_field: value}}}}}
        if version:
            body['version'] = True
        try:
            return es_engine.search(index=self.index_helper.alias_name,
                                    doc_type=self.index_helper.document_type,
                                    body=body, ignore_unavailable=True)
        except Exception as exc:
            LOG.warning(_LW(
                'Error querying %(p)s %(f)s. Error %(exc)s') %
                {'p': path, 'f': field, 'exc': exc})
            return {}
