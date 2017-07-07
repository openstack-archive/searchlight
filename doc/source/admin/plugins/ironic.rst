..
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
Ironic Plugin Guide
*******************

Integration is provided via a plugin. There are multiple configuration
settings required for proper indexing and incremental updates. Some of the
settings are specified in Searchlight configuration files. Others are
provided in other service configuration files.

Searchlight Configuration
=========================

Searchlight resource configuration options are shown below with their
configuration file.

See :ref:`searchlight-plugins` for common options with their default values,
general configuration information, and an example complete configuration.

searchlight.conf
----------------

Plugin: OS::Ironic::Chassis
^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_ironic_chassis]
    notifications_topics_exchanges = ironic_versioned_notifications,ironic

.. note::

    Chassis is not parent resource for node because chassis is not mandatory
    for a node.

Plugin: OS::Ironic::Node
^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_ironic_node]
    notifications_topics_exchanges = ironic_versioned_notifications,ironic

Plugin: OS::Ironic::Port
^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_ironic_port]
    notifications_topics_exchanges = ironic_versioned_notifications,ironic

Ironic Configuration
====================

The ironic services must be configured properly to work with searchlight.

ironic.conf
-----------

Notifications must be configured properly for searchlight to process
incremental updates. Enable notifications using the following::

    [DEFAULT]
    notification_level = info

    [oslo_messaging_notifications]
    driver = messagingv2

.. note::

    Restart ironic api and conductor services after making changes.

Release Notes
=============

``properties`` node's field mapped to ``node_properties`` due to limitation of
older elasticsearch versions.
