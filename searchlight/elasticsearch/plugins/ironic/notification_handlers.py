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
from searchlight.elasticsearch.plugins.ironic import obj_payload
from searchlight.elasticsearch.plugins.ironic import resources
from searchlight.elasticsearch.plugins.ironic import serialize_resource
from searchlight.elasticsearch.plugins.ironic import versioned_payload
from searchlight import pipeline

LOG = logging.getLogger(__name__)


class NodeHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        self.port_helper = kwargs.pop('port_helper')
        super(NodeHandler, self).__init__(*args, **kwargs)

    @classmethod
    def _get_notification_exchanges(cls):
        return ['ironic']

    def get_event_handlers(self):
        return {
            'baremetal.node.power_set.end': self.node_update,
            'baremetal.node.power_set.error': self.node_update,
            'baremetal.node.power_state_corrected.success': self.node_update,

            'baremetal.node.provision_set.start': self.node_update,
            'baremetal.node.provision_set.end': self.node_update,
            'baremetal.node.provision_set.error': self.node_update,
            'baremetal.node.provision_set.success': self.node_update,

            'baremetal.node.create.end': self.node_create_update,
            'baremetal.node.update.end': self.node_create_update,
            'baremetal.node.delete.end': self.node_delete,

            'baremetal.node.maintenance_set.end': self.node_update,

            'baremetal.node.console_set.end': self.node_update,
            'baremetal.node.console_set.error': self.node_update,
            'baremetal.node.console_restore.error': self.node_update
        }

    def get_log_fields(self, event_type, payload):
        return (
            ('version', payload.get('ironic_object.version')),
            ('id', obj_payload(payload)['uuid'])
        )

    @versioned_payload
    def node_create_update(self, event_type, payload, timestamp):
        LOG.debug("Updating node information for %s", payload['uuid'])
        node = serialize_resource(payload, resources.NODE_FIELDS)
        version = self.get_version(node, timestamp)
        self.index_helper.save_document(node, version=version)
        return pipeline.IndexItem(self.index_helper.plugin, event_type,
                                  payload, node)

    @versioned_payload
    def node_update(self, event_type, payload, timestamp):
        node_id = payload['uuid']
        LOG.debug("Updating node information for %s", node_id)
        node = serialize_resource(payload, resources.NODE_FIELDS)
        self.index_helper.update_document(node,
                                          node_id,
                                          update_as_script=False)
        return pipeline.IndexItem(self.index_helper.plugin, event_type,
                                  payload, node)

    @versioned_payload
    def node_delete(self, event_type, payload, timestamp):
        node_id = payload['uuid']
        LOG.debug("Deleting node %s", node_id)

        try:
            ports = self.port_helper.delete_documents_with_parent(node_id)
            deleted = [pipeline.DeleteItem(self.port_helper.plugin,
                                           event_type, payload,
                                           port['_id']) for port in ports]
            self.index_helper.delete_document({'_id': node_id})
            deleted.append(pipeline.DeleteItem(self.index_helper.plugin,
                                               event_type, payload, node_id))
            return deleted
        except Exception as exc:
            LOG.error(
                'Error deleting node %(node_id)s '
                'from index. Error: %(exc)s' %
                {'node_id': node_id, 'exc': exc})


class PortHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['ironic']

    def get_event_handlers(self):
        return {
            'baremetal.port.create.end': self.port_create_update,
            'baremetal.port.update.end': self.port_create_update,
            'baremetal.port.delete.end': self.port_delete,
        }

    def get_log_fields(self, event_type, payload):
        return (
            ('version', payload.get('ironic_object.version')),
            ('id', obj_payload(payload)['uuid'])
        )

    @versioned_payload
    def port_create_update(self, event_type, payload, timestamp):
        LOG.debug("Updating port information for %s", payload['uuid'])
        port = serialize_resource(payload, resources.PORT_FIELDS)
        version = self.get_version(port, timestamp)
        self.index_helper.save_document(port, version=version)
        return pipeline.IndexItem(self.index_helper.plugin, event_type,
                                  payload, port)

    @versioned_payload
    def port_delete(self, event_type, payload, timestamp):
        port_id = payload['uuid']
        LOG.debug("Deleting port %s", port_id)
        try:
            self.index_helper.delete_document_unknown_parent(port_id)
            return pipeline.DeleteItem(self.index_helper.plugin, event_type,
                                       payload, port_id)
        except Exception as exc:
            LOG.error(
                'Error deleting port %(port_id)s '
                'from index. Error: %(exc)s' %
                {'port_id': port_id, 'exc': exc})


class ChassisHandler(base.NotificationBase):
    @classmethod
    def _get_notification_exchanges(cls):
        return ['ironic']

    def get_event_handlers(self):
        return {
            'baremetal.chassis.create.end': self.chassis_create_update,
            'baremetal.chassis.update.end': self.chassis_create_update,
            'baremetal.chassis.delete.end': self.chassis_delete,
        }

    def get_log_fields(self, event_type, payload):
        return (
            ('version', payload.get('ironic_object.version')),
            ('id', obj_payload(payload)['uuid'])
        )

    @versioned_payload
    def chassis_create_update(self, event_type, payload, timestamp):
        LOG.debug("Updating chassis information for %s", payload['uuid'])
        chassis = serialize_resource(payload, resources.CHASSIS_FIELDS)
        version = self.get_version(chassis, timestamp)
        self.index_helper.save_document(chassis, version=version)
        return pipeline.IndexItem(self.index_helper.plugin, event_type,
                                  payload, chassis)

    @versioned_payload
    def chassis_delete(self, event_type, payload, timestamp):
        chassis_id = payload['uuid']
        LOG.debug("Deleting chassis %s", chassis_id)
        try:
            self.index_helper.delete_document({'_id': chassis_id})
            return pipeline.DeleteItem(self.index_helper.plugin, event_type,
                                       payload, chassis_id)
        except Exception as exc:
            LOG.error(
                'Error deleting chassis %(chassis_id)s '
                'from index. Error: %(exc)s' %
                {'chassis_id': chassis_id, 'exc': exc})
