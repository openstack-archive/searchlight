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

from copy import deepcopy
import novaclient.exceptions
from oslo_config import cfg
from oslo_log import log as logging

from elasticsearch import helpers
from searchlight.elasticsearch.plugins import base
from searchlight.elasticsearch.plugins.nova import serialize_nova_flavor
from searchlight.elasticsearch.plugins.nova import serialize_nova_server
from searchlight.elasticsearch.plugins.nova import serialize_server_versioned
from searchlight.elasticsearch.plugins import utils
from searchlight import pipeline

LOG = logging.getLogger(__name__)

SERVERGROUP_RETRIES = 20


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
    _reboot_states = {
        # Hard reboot
        'reboot_pending_hard': 'rebooting_hard',
        'reboot_started_hard': 'reboot_pending_hard',
        # Soft reboot
        'reboot_pending': 'rebooting',
        'reboot_started': 'reboot_pending',
    }
    _shelve_states = {
        'shelving_image_pending_upload': 'shelving',
        'shelving_image_uploading': 'shelving_image_pending_upload',
        # shelving_image_uploading -> shelving_image_pending_upload and
        # shelving_image_pending_upload -> shelving_image_uploading will
        # be ignored.
        'shelving_offloading': 'shelving_image_uploading',
    }
    _unshelve_states = {
        'spawning': 'unshelving'
    }

    # Supported major/minor notification versions. Major changes will likely
    # require code changes.
    notification_versions = {
        'InstanceActionPayload': '1.2',
        'InstanceUpdatePayload': '1.3',
        'InstanceActionVolumeSwapPayload': '1.1',
    }

    @classmethod
    def _get_notification_exchanges(cls):
        return ['nova']

    def get_log_fields(self, event_type, payload):
        return (('id', payload.get('instance_id')),
                ('state', payload.get('state')),
                ('state_description', payload.get('state_description')),
                ('old_task_state', payload.get('old_task_state')),
                ('new_task_state', payload.get('new_task_state')))

    @classmethod
    def get_plugin_opts(cls):
        opts = super(InstanceHandler, cls).get_plugin_opts()
        opts.extend([
            cfg.BoolOpt(
                'use_versioned_notifications',
                help='Expect versioned notifications and ignore unversioned',
                default=True)
        ])
        return opts

    def _use_versioned_notifications(self):
        return self.plugin_options.use_versioned_notifications

    def get_event_handlers(self):
        if not self._use_versioned_notifications():
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
                'compute.instance.reboot.end': self.index_from_api,
                'compute.instance.delete.end': self.delete,

                'compute.instance.shelve.end': self.index_from_api,
                'compute.instance.shelve_offload.end': self.index_from_api,
                'compute.instance.unshelve.end': self.index_from_api,

                'compute.instance.volume.attach': self.index_from_api,
                'compute.instance.volume.detach': self.index_from_api,

                # Removing neutron port events for now; waiting on nova
                # to implement interface notifications as with volumes
                # https://launchpad.net/bugs/1567525
                # bps/nova/+spec/interface-notifications
            }
        # Otherwise listen for versioned notifications!
        # Nova versioned notifications all include the entire payload
        end_events = ['create', 'pause', 'power_off', 'power_on',
                      'reboot', 'rebuild', 'resize', 'restore', 'resume',
                      'shelve', 'shutdown', 'snapshot', 'suspend', 'unpause',
                      'unshelve', 'volume_attach', 'volume_detach']
        notifications = {('instance.%s.end' % ev): self.index_from_versioned
                         for ev in end_events}

        # instance.update has no start or end
        notifications['instance.update'] = self.index_from_versioned

        # This should become soft delete once that is supported
        notifications['instance.delete.end'] = self.delete_from_versioned
        return notifications

    def index_from_update(self, event_type, payload, timestamp):
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
         * state == error -> full index

        There are a set of power state transitions that all follow the same
        kind of structure, with 2 updates and .start and .end events. For these
        events the first update can be a state change and the second ignored.
        They are:
          active -> powering-off -> stopped -> powering-on -> active
          active -> pausing -> paused -> unpausing -> active
          active -> suspending -> suspended -> resuming -> active
        """
        new_state = payload.get('state', None)
        old_state = payload.get('old_state', None)
        new_task_state = payload.get('new_task_state', None)
        old_task_state = payload.get('old_task_state', None)

        # Map provisioning new_task_states to the previous one

        # Default to updating from the API unless we decide otherwise
        update_if_state_matches = None
        ignore_update = False

        if new_state == 'error':
            # There are several ways in which an instance can end up in an
            # error state; it may result in duplicate API requests but it's
            # hard to predict them all
            pass
        elif (new_state == 'active' and old_state == 'active' and
                old_task_state is None and new_task_state is None):
            # This is probably a legitimate server update and should
            # be processed
            pass
        elif new_state == 'building':
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
        elif new_state == 'deleted' and old_task_state == 'deleting':
            # This is always succeeded by a delete.end
            ignore_update = True
        elif new_state == 'active' and new_task_state == 'deleting':
            update_if_state_matches = dict(
                state='active',
                new_task_state=''
            )
        elif new_task_state is not None and new_task_state == old_task_state:
            # Ignore spawning -> spawning for shelved_offloaded instance and
            # shelving_offloading -> shelving_offloading for shelved instance.
            if (new_task_state == 'shelving_offloading' or
                    (new_state == 'shelved_offloaded' and
                     new_task_state == 'spawning')):
                ignore_update = True
            else:
                update_if_state_matches = dict(
                    state=new_state,
                    new_task_state=None)
        elif new_task_state in self._reboot_states:
            update_if_state_matches = dict(
                state=new_state,
                new_task_state=self._reboot_states[new_task_state])
        elif new_task_state in self._shelve_states:
            if (new_state == 'active' or
                    (new_state == 'shelved' and
                     new_task_state == 'shelving_offloading')):
                update_if_state_matches = dict(
                    state='active',
                    new_task_state=self._shelve_states[new_task_state])
        elif new_state == 'shelved_offloaded':
            if new_task_state is not None:
                update_if_state_matches = dict(
                    state=new_state,
                    new_task_state=self._unshelve_states[new_task_state])
            else:
                update_if_state_matches = dict(
                    state='shelved',
                    new_task_state='shelving_offloading')

        if ignore_update:
            LOG.debug("Skipping update or indexing for %s; event contains no "
                      "useful information", payload['instance_id'])
        elif not update_if_state_matches:
            return self.index_from_api(event_type, payload, timestamp)
        elif self.partial_state_updates:
            return self._partial_state_update(
                event_type, payload, update_if_state_matches)
        else:
            LOG.debug("Skipping partial state update for %s; functionality "
                      "is disabled", payload['instance_id'])

    def _partial_state_update(
            self, event_type, payload, update_if_state_matches):
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
            # Don't want to use groovy scripting
            # because there's a high chance it'll be disabled; instead, will
            # get 'n' retrieve ourselves
            preexisting = self.index_helper.get_document(instance_id,
                                                         for_admin=True)

            def should_update(_source):
                for key, value in update_if_state_matches.items():
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
                if should_update(preexisting['_source']):
                    LOG.debug("Performing state update for %s", instance_id)
                    # All preconditions matched; save_document will attempt
                    # to save merged document
                    # TODO(sjmc7) - use the existing update_at to generate
                    # a new timestamp? Still seems kind of made up
                    preexisting['_source'].update(state_field_values)
                    self.index_helper.save_document(
                        preexisting['_source'],
                        version=preexisting['_version'] + 1
                    )
                    return pipeline.IndexItem(self.index_helper.plugin,
                                              event_type,
                                              payload,
                                              preexisting['_source'])

    def index_from_api(self, event_type, payload, timestamp):
        """Index from the nova API"""
        instance_id = payload['instance_id']
        LOG.debug("Updating nova server information for %s", instance_id)
        try:
            serialized_payload = serialize_nova_server(instance_id)
            self.index_helper.save_document(
                serialized_payload,
                version=self.get_version(serialized_payload, timestamp))
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
                                      serialized_payload)
        except novaclient.exceptions.NotFound:
            LOG.warning("Instance %s not found; deleting" % instance_id)

            # Where a notification represents an in-progress delete, we will
            # also receive an 'instance.delete' notification shortly
            deleted = (payload.get('state_description') == 'deleting' or
                       payload.get('state') == 'deleted')
            if not deleted:
                return self.delete(event_type, payload, timestamp)

    def delete(self, event_type, payload, timestamp):
        instance_id = payload['instance_id']
        LOG.debug("Deleting nova instance information for %s", instance_id)
        if not instance_id:
            return

        try:
            version = self.get_version(payload, timestamp,
                                       preferred_date_field='deleted_at')
            self.index_helper.delete_document(
                {'_id': instance_id, '_version': version})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       instance_id
                                       )
        except Exception as exc:
            LOG.error(
                'Error deleting instance %(instance_id)s '
                'from index: %(exc)s' %
                {'instance_id': instance_id, 'exc': exc})

    def index_from_versioned(self, event_type, payload, timestamp):
        notification_version = payload['nova_object.version']
        notification_name = payload['nova_object.name']
        expected_version = self.notification_versions.get(notification_name,
                                                          None)
        if expected_version:
            utils.check_notification_version(
                expected_version, notification_version, notification_name)
        else:
            LOG.warning("No expected notification version for %s; "
                        "processing anyway", notification_name)

        versioned_payload = payload['nova_object.data']
        serialized = serialize_server_versioned(versioned_payload)
        self.index_helper.save_document(
            serialized,
            version=self.get_version(serialized, timestamp))
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  serialized)

    def delete_from_versioned(self, event_type, payload, timestamp):
        payload = payload['nova_object.data']
        instance_id = payload['uuid']
        version = self.get_version(payload, timestamp,
                                   preferred_date_field='deleted_at')
        try:
            version = self.get_version(payload, timestamp,
                                       preferred_date_field='deleted_at')
            self.index_helper.delete_document(
                {'_id': instance_id, '_version': version})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       instance_id
                                       )
        except Exception as exc:
            LOG.error(
                'Error deleting instance %(instance_id)s '
                'from index: %(exc)s' %
                {'instance_id': instance_id, 'exc': exc})


class ServerGroupHandler(base.NotificationBase):
    """Handles nova server group notifications.
    """

    @classmethod
    def _get_notification_exchanges(cls):
        return ['nova']

    def get_event_handlers(self):
        return {
            'servergroup.delete': self.delete,
            'servergroup.create': self.create,
            'servergroup.addmember': self.addmember,
            'compute.instance.delete.end': self.delete_instance
        }

    def _update_server_group_members(self, sg_id, member_id, delete=False):
        # The issue here is that the notification is not complete.
        # We have only a single member that needs to be added to an
        # existing group. A major issue is that we may be updating
        # the ES document while other workers are modifying the rules
        # in the same ES document. This requires an aggressive retry policy,
        # using the "version" field. Since the ES document will have been
        # modified after a conflict, we will need to grab the latest version
        # of the document before continuing. After "retries" number of times,
        # we will admit failure and not try the update anymore.
        LOG.debug("Updating server group member information for %s", sg_id)

        for attempts in range(SERVERGROUP_RETRIES):
            # Read, modify, write of an existing security group.
            doc = self.index_helper.get_document(sg_id)

            if not doc:
                return
            body = doc['_source']
            if not body or 'members' not in body:
                return

            if delete:
                body['members'] = list(filter(
                    lambda r: r != member_id, body['members']))
            else:
                body['members'].append(member_id)

            version = doc['_version']
            try:
                version += 1
                self.index_helper.save_document(body, version=version)
                return body
            except helpers.BulkIndexError as e:
                if e.errors[0]['index']['status'] == 409:
                    # Conflict error, retry with new version of doc.
                    pass
                else:
                    raise

        if attempts == (SERVERGROUP_RETRIES - 1):
            LOG.error('Error updating server group member %(id)s:'
                      ' Too many retries' % {'id': member_id})

    def create(self, event_type, payload, timestamp):
        server_group = deepcopy(payload)
        server_group['id'] = server_group.pop('server_group_id')
        server_group['metadata'] = {}
        server_group['members'] = []
        server_group['updated_at'] = utils.get_now_str()

        LOG.debug("creating nova server group "
                  "information for %s", server_group['id'])
        version = self.get_version(server_group, timestamp)
        self.index_helper.save_document(server_group, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  server_group)

    def addmember(self, event_type, payload, timestamp):
        server_group_id = payload['server_group_id']
        instance_id = payload['instance_uuids'][0]
        server_group = self._update_server_group_members(server_group_id,
                                                         instance_id)
        if server_group:
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
                                      server_group)

    def delete_instance(self, event_type, payload, timestamp):

        # When an instance is deleted from Nova, its' record in
        # InstanceGroup DB was cleaned directly from DB layer in
        # Nova, we should perform sync to keep Searchlight
        # up-to-date with Nova DB.
        instance_id = payload['instance_id']

        query = {'filter': {'term': {'members': instance_id}}}
        search_results = self.index_helper.simple_search(
            query=query, type="OS::Nova::ServerGroup")

        server_group = None
        try:
            result = search_results['hits'][0]
            server_group_id = result['_id']
            server_group = self._update_server_group_members(
                server_group_id,
                instance_id,
                delete=True)
        except IndexError:
            LOG.debug("No nova server group information for instance %s",
                      instance_id)
        if server_group:
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
                                      server_group)

    def delete(self, event_type, payload, timestamp):
        server_group_id = payload['server_group_id']
        LOG.debug("Deleting nova server group information for %s",
                  server_group_id)
        if not server_group_id:
            return

        try:
            self.index_helper.delete_document({'_id': server_group_id})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       server_group_id
                                       )
        except Exception as exc:
            LOG.error(
                'Error deleting server group %(server_group_id)s '
                'from index: %(exc)s' %
                {'server_group_id': server_group_id, 'exc': exc})


class FlavorHandler(base.NotificationBase):
    """Handles nova flavor versioned notifications. The payload samples are:
       https://docs.openstack.org/nova/latest/reference/notifications.html#existing-versioned-notifications
"""

    @classmethod
    def _get_notification_exchanges(cls):
        return ['nova']

    def get_event_handlers(self):
        return {
            'flavor.create': self.create_or_update,
            'flavor.update': self.create_or_update,
            'flavor.delete': self.delete
        }

    def get_log_fields(self, event_type, payload):
        return ('flavorid', payload['nova_object.data']['flavorid']),

    def create_or_update(self, event_type, payload, timestamp):
        flavor = serialize_nova_flavor(payload['nova_object.data'])
        version = self.get_version(flavor, timestamp)

        LOG.debug("Updating nova flavor information for %s", flavor['id'])
        self.index_helper.save_document(flavor, version=version)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  flavor)

    def delete(self, event_type, payload, timestamp):
        flavor = payload['nova_object.data']
        flavor_id = flavor['flavorid']
        LOG.debug("Deleting nova flavor information for %s", flavor_id)

        try:
            self.index_helper.delete_document({'_id': flavor_id})
            return pipeline.DeleteItem(self.index_helper.plugin,
                                       event_type,
                                       payload,
                                       flavor_id)
        except Exception as exc:
            LOG.error('Error deleting flavor %(flavor_id)s '
                      'from index: %(exc)s' %
                      {'flavor_id': flavor_id, 'exc': exc})
