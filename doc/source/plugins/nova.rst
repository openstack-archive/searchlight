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

Plugin: OS::Nova::Server
^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_nova_server]
    enabled = true
    resource_group_name = searchlight

Plugin: OS::Nova::Hypervisor
^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_nova_hypervisor]
    enabled = true

.. note::

    There are no notifications for hypervisor from nova yet, so we recommend
    putting it to its own resource group and scheduling a cron job to re-sync
    with little overhead.

Nova Configuration
==================

The nova services must be configured properly to work with searchlight.

nova.conf
---------

Notifications must be configured properly for searchlight to process
incremental updates. Use the following::

    notification_driver = messaging
    notification_topics = notifications, searchlight_indexer
    rpc_backend = 'rabbit'
    notify_on_state_change=vm_and_task_state

.. note::

    Restart Nova API and Nova scheduler (n-api, n-sch) after making changes.

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
incremental updates. Use the following::

    notification_driver = messaging
    notification_topics = searchlight_indexer
    rpc_backend = 'rabbit'

.. note::

    Restart the Neutron service (q-svc) after making changes.

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

0.2.0.0 (Mitaka)
----------------

The following fields are exposed to adminstrators only for nova instances:
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
