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
import six

from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.nova import serialize_nova_server
from searchlight.i18n import _LE, _LW


LOG = logging.getLogger(__name__)


class InstanceHandler(base.NotificationBase):
    """Handles nova server notifications. These can come as a result of
    a user action (like a name change, state change etc) or as a result of
    periodic auditing notifications nova sends. Because there are so many
    state change notifications, and because currently we're forced to go to
    the nova API for updates, some notifications are processed only as updates
    to the indexed elasticsearch data. Right now those events are part of the
    following operations: boot, poweron/off, suspend/resume, pause/unpause,
                          delete
    """
    partial_state_updates = True

    _state_fields = {'state': 'OS-EXT-STS:vm_state',
                     'new_task_state': 'OS-EXT-STS:task_state'}

    _provisioning_states = {'networking': None,
                            'block_device_mapping': 'networking',
                            'spawning': 'block_device_mapping'}

    @classmethod
    def _get_notification_exchanges(cls):
        return ['nova']

    def get_event_handlers(self):
        return {
            # compute.instance.update seems to be the event set as a
            # result of a state change etc
            'compute.instance.update': self.index_from_update,

            'compute.instance.create.start': self.index_from_api,
            'compute.instance.create.end': self.index_from_api,

            'compute.instance.power_on.end': self.index_from_api,
            'compute.instance.power_off.end': self.index_from_api,
            'compute.instance.resume.end': self.index_from_api,
            'compute.instance.suspend.end': self.index_from_api,
            'compute.instance.pause.end': self.index_from_api,
            'compute.instance.unpause.end': self.index_from_api,

            'compute.instance.shutdown.end': self.index_from_api,
            'compute.instance.delete.end': self.delete,

            'compute.instance.volume.attach': self.index_from_api,
            'compute.instance.volume.detach': self.index_from_api,

            # Removing neutron port events for now; waiting on nova
            # to implement interface notifications as with volumes
            # https://launchpad.net/bugs/1567525
            # https://blueprints.launchpad.net/nova/+spec/interface-notifications
        }

    def index_from_update(self, payload, timestamp):
        """Determine whether or not to process a full update. The updates, and
        how they are processed, are:
        BUILD (state=building unless noted)
         * new_task_state == old_task_state == scheduling -> full index
         * new_task_state == None, old_task_state == scheduling -> ignore
         * new_task_state == old_task_state == None -> ignore
         * new_task_state == networking -> state update
         * new_task_state == block_device_mapping -> state update
         * new_task_state = spawning -> state update
         * state == active, old_task_state == spawning -> ignore

        There are a set of power state transitions that all follow the same
        kind of structure, with 2 updates and .start and .end events. For these
        events the first update can be a state change and the second ignored.
        They are:
          active -> powering-off -> stopped -> powering-on -> active
          active -> pausing -> paused -> unpausing -> active
          active -> suspending -> suspended -> resuming -> active
        """
        new_state = payload.get('state', None)
        new_task_state = payload.get('new_task_state', None)
        old_task_state = payload.get('old_task_state', None)

        # Map provisioning new_task_states to the previous one

        # Default to updating from the API unless we decide otherwise
        update_if_state_matches = None
        ignore_update = False

        if new_state == 'building':
            if old_task_state == 'scheduling' and new_task_state is None:
                # This update arrives after scheduling, and immediately prior
                # to create.start (or an update to error state)
                ignore_update = True
            elif new_task_state is None and old_task_state is None:
                # No new state information - this notification isn't useful
                ignore_update = True
            elif new_task_state in self._provisioning_states:
                # Match against the provisioning states above (networking etc)
                update_if_state_matches = dict(
                    state=new_state,
                    new_task_state=self._provisioning_states[new_task_state])
        elif new_state == 'active' and old_task_state == 'spawning':
            # This is received a few microseconds ahead of instance.create.end
            # and indicates the end of the init sequence; ignore this one in
            # favor of create.end
            ignore_update = True
        elif new_task_state is None and old_task_state is not None:
            # These happen right before a corresponding .end event
            ignore_update = True
        elif new_task_state is not None and new_task_state == old_task_state:
            update_if_state_matches = dict(
                state=new_state,
                new_task_state=None)

        if ignore_update:
            LOG.debug("Skipping update or indexing for %s; event contains no "
                      "useful information", payload['instance_id'])
        elif not update_if_state_matches:
            self.index_from_api(payload, timestamp)
        elif self.partial_state_updates:
            self._partial_state_update(payload, update_if_state_matches)
        else:
            LOG.debug("Skipping partial state update for %s; functionality "
                      "is disabled", payload['instance_id'])

    def _partial_state_update(self, payload, update_if_state_matches):
        """Issue a partial document update that will only affect
        state and task_state fields.
        """
        instance_id = payload['instance_id']
        LOG.debug("Attempting partial state update for %s matching %s",
                  instance_id, update_if_state_matches)

        state_field_values = {
            self._state_fields[k]: payload[k]
            for k in self._state_fields if k in payload
        }

        if state_field_values:
            # Run a partial document update. Don't want to use groovy scripting
            # because there's a high chance it'll be disabled; instead, will
            # get 'n' retrieve ourselves
            preexisting = self.index_helper.get_document(instance_id,
                                                         for_admin=True)

            def should_update(_source):
                for key, value in six.iteritems(update_if_state_matches):
                    key = self._state_fields[key]
                    if key not in _source:
                        LOG.debug("Skipping state update for %s; precondition "
                                  "'%s' not in existing source",
                                  instance_id, key)
                        return False
                    if _source[key] != value:
                        LOG.debug(
                            "Skipping state update for %s; precondition "
                            "'%s' = '%s' doesn't match '%s' in source",
                            instance_id, key, value, _source[key])
                        return False
                return True

            if preexisting:
                current_version = preexisting['_version']
                if should_update(preexisting['_source']):
                    LOG.debug("Performing state update for %s", instance_id)
                    # All preconditions matched; update_document will attempt
                    # to run a partial document update
                    # TODO(sjmc7) - use the existing update_at to generate
                    # a new timestamp? Still seems kind of made up
                    self.index_helper.update_document(
                        state_field_values,
                        instance_id,
                        update_as_script=False,
                        expected_version=current_version)

    def index_from_api(self, payload, timestamp):
        """Index from the nova API"""
        instance_id = payload['instance_id']
        LOG.debug("Updating nova server information for %s", instance_id)
        try:
            serialized_payload = serialize_nova_server(instance_id)
            self.index_helper.save_document(
                serialized_payload,
                version=self.get_version(serialized_payload, timestamp))
        except novaclient.exceptions.NotFound:
            LOG.warning(_LW("Instance %s not found; deleting") % instance_id)

            # Where a notification represents an in-progress delete, we will
            # also receive an 'instance.delete' notification shortly
            deleted = (payload.get('state_description') == 'deleting' or
                       payload.get('state') == 'deleted')
            if not deleted:
                self.delete(payload, timestamp)

    def delete(self, payload, timestamp):
        instance_id = payload['instance_id']
        LOG.debug("Deleting nova instance information for %s", instance_id)
        if not instance_id:
            return

        try:
            version = self.get_version(payload, timestamp,
                                       preferred_date_field='deleted_at')
            self.index_helper.delete_document(
                {'_id': instance_id, '_version': version})
        except Exception as exc:
            LOG.error(_LE(
                'Error deleting instance %(instance_id)s '
                'from index: %(exc)s') %
                {'instance_id': instance_id, 'exc': exc})


class HypervisorHandler(base.NotificationBase):
    """Handles nova hypervisor notifications.
    """

    @classmethod
    def _get_notification_exchanges(cls):
        return ['nova']

    def get_event_handlers(self):
        # TODO(lyj): Currently there is no notification for hypervisor,
        #            this needs to be changed once the notification for
        #            hypervisor in nova is implemented:
        # https://blueprints.launchpad.net/nova/+spec/hypervisor-notification
        return {}
