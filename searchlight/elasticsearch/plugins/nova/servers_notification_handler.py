# Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
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

import novaclient.exceptions
from oslo_log import log as logging

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.nova import serialize_nova_server
from searchlight import i18n


LOG = logging.getLogger(__name__)
_LW = i18n._LW
_LE = i18n._LE


class InstanceHandler(base.NotificationBase):
    """Handles nova server notifications. These can come as a result of
    a user action (like a name change, state change etc) or as a result of
    periodic auditing notifications nova sends
    """

    @classmethod
    def _get_notification_exchanges(cls):
        return ['nova', 'neutron']

    def get_event_handlers(self):
        return {
            # compute.instance.update seems to be the event set as a
            # result of a state change etc
            'compute.instance.update': self.create_or_update,
            'compute.instance.exists': self.create_or_update,
            'compute.instance.create.end': self.create_or_update,
            'compute.instance.power_on.end': self.create_or_update,
            'compute.instance.power_off.end': self.create_or_update,
            'compute.instance.delete.end': self.delete,

            # Neutron events
            'port.create.end': self.update_from_neutron,
            # TODO(sjmc7) Remind myself why i commented this out,
            # and also whether neutron events should be separate
            # 'port.delete.end': self.update_neutron_ports,
        }

    def create_or_update(self, payload):
        instance_id = payload['instance_id']
        LOG.debug("Updating nova server information for %s", instance_id)
        self._update_instance(instance_id)

    def update_from_neutron(self, payload):
        instance_id = payload['port']['device_id']
        LOG.debug("Updating server %s from neutron notification",
                  instance_id)
        if not instance_id:
            return
        self._update_instance(instance_id)

    def _update_instance(self, instance_id):
        try:
            payload = serialize_nova_server(instance_id)
        except novaclient.exceptions.NotFound:
            LOG.warning(_LW("Instance %s not found; deleting") % instance_id)
            try:
                self.engine.delete(
                    index=self.index_name,
                    doc_type=self.document_type,
                    id=instance_id
                )
            except Exception as e:
                LOG.error(_LE(
                    'Error deleting instance %(instance_id)s '
                    'from index: %(exc)s') % (instance_id, e))
            return

        self.engine.index(
            index=self.index_name,
            doc_type=self.document_type,
            body=payload,
            id=instance_id
        )

    def delete(self, payload):
        instance_id = payload['instance_id']
        LOG.debug("Deleting nova instance information for %s", instance_id)
        if not instance_id:
            return

        self.engine.delete(
            index=self.index_name,
            doc_type=self.document_type,
            id=instance_id
        )
