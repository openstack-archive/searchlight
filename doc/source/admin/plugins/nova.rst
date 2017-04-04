..
    c) Copyright 2015 Hewlett-Packard Development Company, L.P.

    Licensed under the Apache License, Version 2.0 (the "License"); you may
    not use this file except in compliance with the License. You may obtain
    a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
    License for the specific language governing permissions and limitations
    under the License.

*****************
Nova Plugin Guide
*****************

Integration is provided via a plugin. There are multiple configuration
settings required for proper indexing and incremental updates. Some of the
settings are specified in Searchlight configuration files. Others are
provided in other service configuration files.

Searchlight Configuration
=========================

Searchlight resource configuration options are shown below with their
configuration file and default values.

See :ref:`searchlight-plugins` for common options with their default values,
general configuration information, and an example complete configuration.

.. note::

    Unless you are changing to a non-default value, you do not need to
    specify any of the following configuration options.

searchlight.conf
----------------

Nova microversions
^^^^^^^^^^^^^^^^^^
::

    [service_credentials:nova]
    compute_api_version = 2.1

.. note::

    Nova adds/removes fields using microversion mechanism, check
    https://docs.openstack.org/nova/latest/api_microversion_history.html
    for detailed Nova microversion history.

Plugin: OS::Nova::Server
^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_nova_server]
    enabled = true
    resource_group_name = searchlight
    notifications_topics_exchanges = versioned_notifications,nova
    use_versioned_notifications = true

Plugin: OS::Nova::Hypervisor
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This plugin represents each of the Nova compute nodes.

::

    [resource_plugin:os_nova_hypervisor]
    enabled = true
    resource_group_name = sl_without_notification

.. note::

    There are no notifications from the compute nodes ("hypervisors") from
    nova yet, so we recommend putting it in its own resource group and
    scheduling a cron job to periodically re-sync. This will create a very
    low overhead way to keep the index up to date. The index latency will be
    dependent on how often you re-sync the data.

Plugin: OS::Nova::Flavor
^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_nova_flavor]
    enabled = true
    resource_group_name = searchlight
    notifications_topics_exchanges = versioned_notifications,nova

.. note::

    The notifications topic for flavors is versioned_notifications, so we
    need to config notifications_topics_exchanges with value
    'versioned_notifications,nova' in order to get the related versioned
    notifications from nova.

Plugin: OS::Nova::SeverGroup
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_nova_servergroup]
    enabled = true
    resource_group_name = searchlight

.. note::

    The return value of os-server-groups API from nova doesn't contain
    project and user information before nova API microversion v2.13,
    thus the index cannot been searched by particular project.

Nova Configuration
==================

The nova services must be configured properly to work with searchlight.

nova.conf
---------

Notifications must be configured properly for searchlight to process
incremental updates. Enable notifications using the following::

    [oslo_messaging_notifications]
    driver = messagingv2

    [notifications]
    notify_on_state_change = vm_and_task_state
    # notification_format = versioned

.. note::

    Restart Nova API and Nova scheduler (n-api, n-sch) after making changes.
    See :ref:`plugin_notifications` for more information on
    notification topics.

    The default setting for notification_format is 'both' which sends both
    versioned and unversioned notifications. Searchlight uses
    'use_versioned_notifications' to decide which to use.

local.conf (devstack)
---------------------

The settings above may be automatically configured by ``stack.sh``
by adding them to the following post config section in devstack.
Just place the following in local.conf and copy the above settings
underneath it.::

    [[post-config|$NOVA_CONF]]
    [DEFAULT]

Neutron Configuration
=====================

Since changes to Neutron can affect Nova instances you may optionally turn on
notifications for Neutron.  If you do not, networking changes will only be
picked up by Searchlight when notifications are received from Nova.

neutron.conf
------------

Notifications must be configured properly for searchlight to process
incremental updates. Enable notifications using the following::

    [oslo_messaging_notifications]
    driver = messagingv2

.. note::

    Restart the Neutron api service (q-svc) after making changes.
    See :ref:`plugin_notifications` for more information on
    notification topics.

local.conf (devstack)
---------------------

The settings above may be automatically configured by ``stack.sh``
by adding them to the following post config section in devstack.
Just place the following in local.conf and copy the above settings
underneath it.::

  [[post-config|$NEUTRON_CONF]]
  [DEFAULT]

Release Notes
=============

1.0.0.0 (Newton)
----------------
In order to reduce the impact on the nova API, changes have been made to the
way notifications are processed. Currently searchlight has to retrieve nova
server information from nova because the notifications alone are missing
several pieces of information. Prior to Newton this meant up to 7 API requests
during a server boot. During Newton this was changed. There will now be one
initial nova request prior to the scheduler, one when the
``instance.create.start`` notification is received, one when networking is
established and one after the instance has booted and run any init scripts.
Other notifications during boot will update only the server status.

0.2.0.0 (Mitaka)
----------------

Notifications must be configured properly for searchlight to process
incremental updates. Searchlight must use its own topic. Use the following::

    notification_driver = messaging
    notification_topics = searchlight_indexer

The following fields are exposed to administrators only for nova instances:
 * OS-EXT-SRV-ATTR:*

Additional properties can be similarly protected with the `admin_only_fields`
under each plugin's configuration section. Glob-like patterns are supported.
For instance::

    [resource_plugin:os_nova_server]
    admin_only_fields=OS-EXT-STS:vm_state

See: ADMIN_ONLY_FIELDS in:
* searchlight/elasticsearch/plugins/nova/servers.py

0.1.0.0 (Liberty)
-----------------

All OS-EXT-SRV-ATTR:.* properties are filtered out from search results
for non-admin users. This is not a configuration option in this release.
To change this or filter out additional properties, you must change the
plugin code to add additional properties.

See: ADMIN_ONLY_PROPERTIES in searchlight/elasticsearch/plugins/nova/servers.py
