..
    c) Copyright 2016 Hewlett-Packard Enterprise Development Company, L.P.

    Licensed under the Apache License, Version 2.0 (the "License"); you may
    not use this file except in compliance with the License. You may obtain
    a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
    License for the specific language governing permissions and limitations
    under the License.

*******************
Cinder Plugin Guide
*******************

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

Plugin: OS::Cinder::Volume
^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_cinder_volume]
    enabled = true
    resource_group_name = searchlight

Plugin: OS::Cinder::Snapshot
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_cinder_snapshot]
    enabled = true
    resource_group_name = searchlight

Cinder Configuration
====================

Cinder sends notifications on create/update/delete actions on the
resources that it implements. Currently Searchlight supports indexing
for volumes and snapshots of volumes. Backup support will be added but
some changes to the cinder backup API is required first.

cinder.conf
-----------

Notifications must be configured properly for searchlight to process
incremental updates. Enable notifications using the following::

    [oslo_messaging_notifications]
    driver = messagingv2

.. note::

    Restart the Cinder api service (c-api) after making changes.
    See :ref:`plugin_notifications` for more information on
    notification topics.

local.conf (devstack)
---------------------

The settings above may be automatically configured by ``stack.sh``
by adding them to the following post config section in devstack.
Just place the following in local.conf and copy the above settings
underneath it.::

  [[post-config|$CINDER_CONF]]
  [DEFAULT]

Release Notes
=============

0.2.0.0 (Mitaka)
----------------

Notifications must be configured properly for searchlight to process
incremental updates. Searchlight must use its own topic. Use the following::

    notification_driver = messaging
    notification_topics = searchlight_indexer

The following fields are exposed to administrators only for cinder volumes:
 * os-vol-mig-status-attr:*
 * os-vol-host-attr:*
 * migration

Additional properties can be similarly protected with the `admin_only_fields`
under each plugin's configuration section. Glob-like patterns are supported.
For instance::

    [resource_plugin:os_cinder_volume]
    admin_only_fields=status,bootable

See: ADMIN_ONLY_FIELDS in:
* searchlight/elasticsearch/plugins/cinder/volumes.py
