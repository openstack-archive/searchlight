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

from elasticsearch import helpers
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.helper import USER_ID_SUFFIX
from searchlight.elasticsearch.plugins.neutron import add_rbac
from searchlight.elasticsearch.plugins.neutron import serialize_floatingip
from searchlight.elasticsearch.plugins.neutron import serialize_network
from searchlight.elasticsearch.plugins.neutron import serialize_port
from searchlight.elasticsearch.plugins.neutron import serialize_router
from searchlight.elasticsearch.plugins.neutron import serialize_security_group
from searchlight.elasticsearch.plugins.neutron import serialize_subnet
from searchlight.elasticsearch.plugins import openstack_clients
from searchlight.elasticsearch.plugins import utils
from searchlight import pipeline

LOG = logging.getLogger(__name__)

SECGROUP_RETRIES = 20
RBAC_VALID_ACTIONS = ["access_as_shared", "access_as_external"]


class NetworkHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['neutron']

    def get_event_handlers(self):
        return {
            'network.create.end': self.create_or_update,
            'network.update.end': self.create_or_update,
            'network.delete.end': self.delete,
            'rbac_policy.create.end': self.rbac_create,
            'rbac_policy.delete.end': self.rbac_delete
        }

    def get_log_fields(self, event_type, payload):
        # Delete and create/update notifications are different structures
        if 'network' in payload:
            return ('id', payload['network'].get('id')),
        elif 'network_id' in payload:
            return ('id', payload['network_id']),
        elif 'rbac_policy' in payload:
            return (
                ('network_id', payload['rbac_policy'].get('object_id')),
                ('target_tenant',
                 payload['rbac_policy'].get('target_tenant')),
                ('object_type',
                 payload['rbac_policy'].get('object_type')))
        elif 'rbac_policy_id' in payload:
            return ('rbac_policy_id', payload['rbac_policy_id']),
        return ()

    def create_or_update(self, event_type, payload, timestamp):
        network_id = payload['network']['id']
        LOG.debug("Updating network information for %s", network_id)

        # Neutron doesn't give us any date/time information
        network = serialize_network(payload['network'])
        version = self.get_version(network, timestamp)

        self.index_helper.save_document(network, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  network)

    def delete(self, event_type, payload, timestamp):
        network_id = payload['network_id']
        LOG.debug("Deleting network information for %s", network_id)
        try:
            # Note that it's not necessary to delete ports; neutron will not
            # allow deletion of a network that has ports assigned on it
            self.index_helper.delete_document({'_id': network_id})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       network_id)
        except Exception as exc:
            LOG.error(
                'Error deleting network %(network_id)s '
                'from index. Error: %(exc)s' %
                {'network_id': network_id, 'exc': exc})

    def rbac_create(self, event_type, payload, timestamp):
        """RBAC policy is making a network visible to users in a specific
           tenant. Previously this network was not visible to users in that
           tenant. We will want to add this tenant to the members list.
           Also add the RBAC policy.
        """
        valid_types = ["network"]

        event_type = payload['rbac_policy']['object_type']
        action = payload['rbac_policy']['action']
        if action not in RBAC_VALID_ACTIONS or event_type not in valid_types:
            # I'm bored. Nothing that concerns nor interests us.
            return

        network_id = payload['rbac_policy']['object_id']
        target_tenant = payload['rbac_policy']['target_tenant']
        policy_id = payload['rbac_policy']['id']
        LOG.debug("Adding RBAC policy for network %s with tenant %s",
                  network_id, target_tenant)

        # Read, modify, write an existing network document. Grab and modify
        # the admin version of the document. When saving the document it will
        # be indexed for both admin and user.
        doc = self.index_helper.get_document(network_id, for_admin=True)

        if not doc or not doc['_source']:
            LOG.error('Error adding rule to network. Network %(id)s '
                      'does not exist.' % {'id': network_id})
            return

        body = doc['_source']

        # Update network with RBAC policy.
        add_rbac(body, target_tenant, policy_id)

        # Bump version for race condition prevention. Use doc and not
        # body, since '_version' is outside of '_source'.
        version = doc['_version'] + 1
        self.index_helper.save_document(body, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  body)

    def rbac_delete(self, event_type, payload, timestamp):
        """RBAC policy is making a network invisible to users in specific
           tenant. Previously this network was visible to users in that
           tenant. We will remove this tenant from the members list.
           Also remove the RBAC policy.
        """
        policy_id = payload['rbac_policy_id']

        # Read, modify, write an existing network document. For both the
        # admin and user version of the document.

        # Find all documents (admin and user) with the policy ID.
        docs = self.index_helper.get_docs_by_nested_field(
            "rbac_policy", "rbac_id", policy_id, version=True)

        if not docs or not docs['hits']['hits']:
            return

        for doc in docs['hits']['hits']:
            if doc['_id'].endswith(USER_ID_SUFFIX):
                # We only want to use the admin document.
                continue
            body = doc['_source']

            target_tenant = None
            policies = body['rbac_policy']
            for p in policies:
                if p.get('rbac_id') == policy_id:
                    target_tenant = p['target_tenant']

            # Remove target_tenant from members list.
            members_list = (body['members'])
            if target_tenant in members_list:
                members_list.remove(target_tenant)
                body['members'] = members_list

            # Remove RBAC policy.
            new_list = [p for p in policies if p.get('rbac_id') != policy_id]
            body['rbac_policy'] = new_list

            # Bump version for race condition prevention. Use doc and not
            # body, since '_version' is outside of '_source'.
            version = doc['_version'] + 1
            self.index_helper.save_document(body, version=version)
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
                                      body)


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

    def create_or_update(self, event_type, payload, timestamp):
        port_id = payload['port']['id']

        if payload['port'].get('device_owner', None) == 'network:dhcp':
            # TODO(sjmc7): Remove this once we can get proper notifications
            # about DHCP ports.
            #  See https://bugs.launchpad.net/searchlight/+bug/1558790
            LOG.info("Skipping notification for DHCP port %s. If neutron "
                     "is sending notifications for DHCP ports, the "
                     "Searchlight plugin should be updated to process "
                     "them.", port_id)
            return

        LOG.debug("Updating port information for %s", port_id)

        # Version doesn't really make a huge amount of sense here but
        # is better than nothing
        port = serialize_port(payload['port'])
        version = self.get_version(port, timestamp)

        self.index_helper.save_document(port, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  port)

    def delete_port(self, event_type, payload, timestamp):
        return self.delete(event_type, payload, payload['port_id'])

    def delete(self, event_type, payload, port_id):
        LOG.debug("Deleting port information for %s; finding routing", port_id)
        try:
            self.index_helper.delete_document_unknown_parent(port_id)
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       port_id)
        except Exception as exc:
            LOG.error(
                'Error deleting port %(port_id)s '
                'from index. Error: %(exc)s' %
                {'port_id': port_id, 'exc': exc})

    def create_or_update_from_interface(self, event_type, payload, timestamp):
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
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  serialized
                                  )

    def delete_from_interface(self, event_type, payload, timestamp):
        """The partner of create_or_update_from_interface. There's no separate
        port deletion notification.
        """
        port_id = payload['router_interface']['port_id']
        LOG.debug("Deleting port %s from router interface", port_id)
        return self.delete(event_type, payload, port_id)


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

    def create_or_update(self, event_type, payload, timestamp):
        subnet_id = payload['subnet']['id']
        LOG.debug("Updating subnet information for %s", subnet_id)
        subnet = serialize_subnet(payload['subnet'])

        version = self.get_version(subnet, timestamp)
        self.index_helper.save_document(subnet, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  subnet)

    def delete(self, event_type, payload, timestamp):
        subnet_id = payload['subnet_id']
        LOG.debug("Deleting subnet information for %s; finding routing",
                  subnet_id)
        try:
            self.index_helper.delete_document_unknown_parent(subnet_id)
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       subnet_id)
        except Exception as exc:
            LOG.error(
                'Error deleting subnet %(subnet_id)s '
                'from index: %(exc)s' %
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

    def create_or_update(self, event_type, payload, timestamp):
        router_id = payload['router']['id']
        LOG.debug("Updating router information for %s", router_id)
        router = serialize_router(
            payload['router'],
            updated_at=utils.timestamp_to_isotime(timestamp))
        version = self.get_version(router, timestamp)
        self.index_helper.save_document(router, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  router)

    def delete(self, event_type, payload, timestamp):
        router_id = payload['router_id']
        LOG.debug("Deleting router information for %s", router_id)
        try:
            self.index_helper.delete_document({'_id': router_id})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       router_id)
        except Exception as exc:
            LOG.error(
                'Error deleting router %(router)s '
                'from index: %(exc)s' %
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

    def create_or_update(self, event_type, payload, timestamp):
        fip_id = payload['floatingip']['id']
        LOG.debug("Updating floatingip information for %s", fip_id)
        floatingip = serialize_floatingip(
            payload['floatingip'],
            updated_at=utils.timestamp_to_isotime(timestamp))
        version = self.get_version(floatingip, timestamp)
        self.index_helper.save_document(floatingip, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  floatingip)

    def delete(self, event_type, payload, timestamp):
        fip_id = payload['floatingip_id']
        LOG.debug("Deleting floatingip information for %s", fip_id)
        try:
            self.index_helper.delete_document({'_id': fip_id})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       fip_id)
        except Exception as exc:
            LOG.error(
                'Error deleting floating ip %(fip)s '
                'from index: %(exc)s' %
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

    def create_or_update_group(self, event_type, payload, timestamp):
        group_name = payload['security_group']['name']
        sec_id = payload['security_group']['id']
        LOG.debug("Updating security group information for %(grp)s (%(sec)s)" %
                  {'grp': group_name, 'sec': sec_id})

        # Version doesn't really make sense for security groups,
        # but we need to normalize the fields.
        doc = serialize_security_group(payload['security_group'])
        version = self.get_version(doc, timestamp)

        self.index_helper.save_document(doc, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  doc)

    def delete_group(self, event_type, payload, timestamp):
        sec_id = payload['security_group_id']
        LOG.debug("Deleting security group information for %s", sec_id)
        try:
            self.index_helper.delete_document({'_id': sec_id})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       sec_id)
        except Exception as exc:
            LOG.error(
                'Error deleting security_group %(sec_id)s. Error: %(exc)s' %
                {'sec_id': sec_id, 'exc': exc})

    def create_or_update_rule(self, event_type, payload, timestamp):
        # The issue here is that the notification is not complete.
        # We have only a single rule that needs to be added to an
        # existing group. A major issue is that we may be updating
        # the ES document while other workers are modifying the rules
        # in the same ES document. This requires an aggressive retry policy,
        # using the "version" field. Since the ES document will have been
        # modified after a conflict, we will need to grab the latest version
        # of the document before continuing. After "retries" number of times,
        # we will admit failure and not try the update anymore.
        # NB: Most of the looping logic is the same as in "delete_rule".
        #     The read/modify the ES document is different. If the logic
        #     changes, please make the changes there.
        group_id = payload['security_group_rule']['security_group_id']
        LOG.debug("Updating security group rule information for %s", group_id)

        for attempts in range(SECGROUP_RETRIES):
            # Read, modify, write of an existing security group.
            doc = self.index_helper.get_document(group_id)

            if not doc:
                return
            body = doc['_source']
            if not body or 'security_group_rules' not in body:
                return

            body['security_group_rules'].append(payload['security_group_rule'])

            version = doc['_version']
            try:
                version += 1
                self.index_helper.save_document(body, version=version)
                return pipeline.IndexItem(self.index_helper.plugin,
                                          event_type,
                                          payload,
                                          body)
            except helpers.BulkIndexError as e:
                if e.errors[0]['index']['status'] == 409:
                    # Conflict error, retry with new version of doc.
                    pass
                else:
                    raise

        if attempts == (SECGROUP_RETRIES - 1):
            LOG.error('Error adding security group rule %(id)s:'
                      ' Too many retries' % {'id': group_id})

    def delete_rule(self, event_type, payload, timestamp):
        # See comment for create_or_update_rule() for details.
        rule_id = payload['security_group_rule_id']
        LOG.debug("Updating security group rule information for %s", rule_id)

        field = 'security_group_rules'

        # Read, modify, write of an existing security group.
        # To avoid a race condition, we are searching for the document
        # in a round-about way. Outside of the retry loop, we will
        # search for the document and save the document ID. This way we
        # do not need to search inside the loop. We will access the document
        # directly by the ID which will always return the latest version.
        orig_doc = self.index_helper.get_docs_by_nested_field(
            "security_group_rules", "id", rule_id, version=True)
        if not orig_doc:
            return
        doc_id = orig_doc['hits']['hits'][0]['_id']
        doc = orig_doc['hits']['hits'][0]
        for attempts in range(SECGROUP_RETRIES):
            body = doc['_source']
            if not body or field not in body:
                return

            body[field] = \
                list(filter(lambda r: r['id'] != rule_id, body[field]))

            version = doc['_version']
            try:
                version += 1
                self.index_helper.save_document(body, version=version)
                return pipeline.IndexItem(self.index_helper.plugin,
                                          event_type,
                                          payload,
                                          body)
            except helpers.BulkIndexError as e:
                if e.errors[0]['index']['status'] == 409:
                    # Conflict. Retry with new version.
                    doc = self.index_helper.get_document(doc_id)
                    if not doc:
                        return
                else:
                    raise

        if attempts == (SECGROUP_RETRIES - 1):
            LOG.error('Error deleting security group rule %(id)s:'
                      ' Too many retries' % {'id': rule_id})
