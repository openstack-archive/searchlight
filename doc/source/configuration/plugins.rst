..
      Copyright 2015 Hewlett-Packard Development Company, L.P.
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

.. _searchlight-plugins:

Searchlight Plugin Documentation
================================

The search service determines the types of information that is searchable
via a plugin mechanism.

.. _installing-plugins:

Installing Plugins
------------------

Plugins must be registered in ``setup.cfg``.

Within ``setup.cfg`` the setting within ``[entry_points]`` named
``searchlight.index_backend`` should list the plugin for each available
indexable type. After making a change, it's necessary to re-install the
python package (for instance with ``pip install -e .``).

Each plugin registered in ``setup.cfg`` is enabled by default. Typically it
should only be necessary to modify ``setup.cfg`` if you are installing a new
plugin. It is not necessary to modify ``[entry_points]`` to temporarily
enable or disable installed plugins. Once they are installed, they can be
disabled, enabled and configured in the ``searchlight.conf`` file.

Configuring Plugins
-------------------

After installation, plugins are configured in ``searchlight.conf``.

.. note::

    After making changes to ``searchlight.conf`` you must perform the
    actions indicated in the tables below.

    1. ``Restart services``: Restart all running ``searchlight-api`` *and*
       ``searchlight-listener`` processes.

    2. ``Re-index affected types``: You will need to re-index any resource
       types affected by the change. (See :doc:`../admin/indexingservice`).

.. note::

    Unless you are changing to a non-default value, you do not need to
    specify any of the following configuration options.

.. _end-to-end-plugin-configuration-example:

End to End Configuration Example
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following shows a sampling of various configuration options in
``searchlight.conf``. These are **NOT** necessarily recommended
or default configuration values. They are intended for exemplary purposes only.
Please read the rest of the guide for detailed information.::

    [listener]
    notifications_pool = searchlight

    [resource_plugin]
    resource_group_name = searchlight
    # include_region_name = True

    [service_credentials:nova]
    compute_api_version = 2.1

    [resource_plugin:os_nova_server]
    enabled = True
    admin_only_fields = OS-EXT-SRV*,OS-EXT-STS:vm_state

    [resource_plugin:os_nova_hypervisor]
    enabled = True

    [resource_plugin:os_nova_flavor]
    enabled = True

    [resource_plugin:os_nova_servergroup]
    enabled = False

    [resource_plugin:os_glance_image]
    enabled = True
    # override_region_name = Region1,Region2

    [resource_plugin:os_glance_metadef]
    enabled = True

    [resource_plugin:os_cinder_volume]
    enabled = True

    [resource_plugin:os_cinder_snapshot]
    enabled = True

    [resource_plugin:os_neutron_net]
    enabled = True
    admin_only_fields=admin_state_up,status

    [resource_plugin:os_neutron_port]
    enabled = True

    [resource_plugin:os_neutron_security_group]
    enabled = True

    [resource_plugin:os_designate_zone]
    enabled = False

    [resource_plugin:os_designate_recordset]
    enabled = False

    [resource_plugin:os_swift_account]
    enabled = False

    [resource_plugin:os_swift_container]
    enabled = False

    [resource_plugin:os_swift_object]
    enabled = False

Common Plugin Configuration Options
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are common configuration options that all plugins honor. They are split
between *global*, *inheritable* and *non-inheritable* options.

**Global** plugin configuration options apply to all plugins and cannot be
overridden by an individual plugin.

**Inheritable** common configuration options may be specified in a default
configuration group of ``[resource_plugin]`` in ``searchlight.conf`` and
optionally overridden in a specific plugin's configuration. For example::

    [resource_plugin]
    resource_group_name = searchlight

    [resource_plugin:os_nova_server]
    resource_group_name = searchlight-nova-servers

**Non-Inheritable** common configuration options are honored by all plugins,
but must be specified directly in that plugin's configuration group. They
are not inherited from the ``[resource_plugin]`` configuration group. For
example::

    [resource_plugin:os_glance_image]
    enabled = false

.. _plugin_notifications:

Notifications
.............

There are two ways to configure services to send notifications that
Searchlight can receive. The recommended method is to configure
Searchlight to use the notification topic that each service is already
configured to use and then to allow Searchlight to consume messages from
that topic using a pool, touched on in the `messaging documentation`_.
Searchlight uses this configuration by default.

.. _`messaging documentation`: https://docs.openstack.org/oslo.messaging/latest/configuration/opts.html

**Topics**

Searchlight defaults to using the oslo notification topic of
``notifications``. This is the oslo default topic which most services also
use to broadcast their notifications. You will need to change the topic in both
``searchlight.conf`` and the various service configuration files if you want
to modify the topic used by Searchlight. Each plugin can use a different topic.

Notification topics are a special case. It is possible to override
the notification ``topic`` as a shared setting; it is also possible to
override ``<topic>,<exchange>`` pairs per-plugin in the case where some
services are using different topics. For instance, in a setup where (for
example) neutron is using a separate notification topic::

    [resource_plugin]
    notifications_topic = searchlight_indexer

    [resource_plugin:os_nova_server]
    notifications_topics_exchanges = searchlight_indexer,nova
    notifications_topics_exchanges = another-topic,neutron

If you override one service topic, you must provide topic,exchange pairs
for all service notifications a plugin supports.

**Pools**

In addition, Searchlight uses a notification pool. This allows Searchlight
to listen on the same topic to which other services are listening while
ensuring that Searchlight still gets its own copy of each notification. The
default notification pool is set to ``searchlight``. This is set using the
``notifications_pool`` setting in the ``[listener]`` configuration group.
Example::

    [listener]
    notification_pools = searchlight

See :ref:`individual-plugin-configuration` for more information and examples
on individual plugin configuration.

Publishers
..........

Searchlight supports configuration of publishers which push enriched
notification info to other external systems. To use this feature, you must first
register publishers in ``setup.cfg``. This is similar to
:ref:`installing-plugins` action. Within ``setup.cfg`` the setting within
``[entry_points]`` named ``searchlight.publishers`` should list publishers for
plugins to use. Don't forget to re-install the python package(`pip install -e`)
if you have made changes to publisher entry points.
Example::

    [entry_points]
    searchlight.publisher =
        log_publisher = searchlight.publisher.log.LogPublisher

Publishers can be specified in a default configuration group of `[resource_plugin]`
in `searchlight.conf` or overridden in a specific plugin's configuration.
Example::

    [resource_plugin]
    publishers = log_publisher

Currently publishers only work for incremental updates. Bulk api updates are not
supported.

Global Configuration Options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

+---------------------+---------------+-------------------------------------+---------------------------+
| Option              | Default value | Description                         | Action(s) Required        |
+=====================+===============+=====================================+===========================+
| resource_group_name | searchlight   | Determines the ElasticSearch index  |                           |
|                     |               | and alias where documents will be   | | Restart services        |
|                     |               | stored. Index names will be         | | Re-index all types      |
|                     |               | suffixed with a timestamp. Group    |                           |
|                     |               | name must consist of only lowercase |                           |
|                     |               | alphanumeric characters and         |                           |
|                     |               | underscores. The first character    |                           |
|                     |               | cannot be an underscore.            |                           |
+---------------------+---------------+-------------------------------------+---------------------------+
| include_region_name |               | Defined for all plugins. Controls   | | Restart services        |
|                     |               | whether or not to include           | | Reindex all             |
|                     |               | region_name as a mapping field and  |                           |
|                     |               | in each document. Defaults to off.  |                           |
+---------------------+---------------+-------------------------------------+---------------------------+

.. note::

    Sorting on fields across resource types(plugins), with each plugin specifying a different resource group
    name will cause errors if sort-by fields are not defined in each resource type.
    See :ref:`using-resource-groups` for more information on how to sort across different resource groups

Inheritable Common Configuration Options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

+---------------------+---------------+-------------------------------------+---------------------------+
| Option              | Default value | Description                         | Action(s) Required        |
+=====================+===============+=====================================+===========================+
| mapping_use\_       |               | Use doc_values to store documents   |                           |
|    doc_values       | true          | rather than fieldata. doc_values    | | Full re-index           |
|                     |               | has some advantages, particularly   |                           |
|                     |               | around memory usage.                |                           |
+---------------------+---------------+-------------------------------------+---------------------------+
| notifications_topic | notifications | The oslo.messaging topic on which   | Restart listener          |
|                     |               | services send notifications. Each   |                           |
|                     |               | plugin defines a list of exchanges  |                           |
|                     |               | to which it will subscribe.         |                           |
+---------------------+---------------+-------------------------------------+---------------------------+
| publishers          |               | Plugin can have multiple publishers | Restart listener          |
|                     |               | separated by commas. Each publisher |                           |
|                     |               | will receive enriched notifications |                           |
|                     |               | once plugin subscribed events come. |                           |
+---------------------+---------------+-------------------------------------+---------------------------+

Non-Inheritable Common Configuration Options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

+---------------------+---------------+-------------------------------------+---------------------------+
| Option              | Default value | Description                         | Action(s) Required        |
+=====================+===============+=====================================+===========================+
| enabled             | true          | An installed plugin may be enabled  | | Restart services        |
|                     |               | (true) or disabled (false). When    | | Re-index affected types |
|                     |               | disabled, it will not be available  |                           |
|                     |               | for bulk indexing, notification     |                           |
|                     |               | listening, or searching.            |                           |
+---------------------+---------------+-------------------------------------+---------------------------+
| admin_only_fields   | <none>        | A comma separated list of fields    | | Restart services        |
|                     |               | (wildcards allowed) that are only   | | Re-index affected types |
|                     |               | visible to administrators, and only |                           |
|                     |               | searchable by administrators. Non-  |                           |
|                     |               | administrative users will not be    |                           |
|                     |               | able to see or search on these      |                           |
|                     |               | fields.                             |                           |
|                     |               | These fields are typically          |                           |
|                     |               | specified for search performance,   |                           |
|                     |               | search accuracy, or security        |                           |
|                     |               | reasons.                            |                           |
|                     |               | or security reasons.                |                           |
|                     |               | If a plugin has a hard-coded        |                           |
|                     |               | mapping for a specific field, it    |                           |
|                     |               | will take precedence over this      |                           |
|                     |               | configuration option.               |                           |
+---------------------+---------------+-------------------------------------+---------------------------+
| notifications\_     | <none>        | Override topic,exchange pairs (see  | | Restart services        |
|  topics_exchanges   |               | note above). Use when services      |                           |
|                     |               | output notifications on dissimilar  |                           |
|                     |               | topics.                             |                           |
+---------------------+---------------+-------------------------------------+---------------------------+
| override_region_name| <none>        | Specifies a region_name to be used  | | Restart services        |
|                     |               | instead of one configured in        |                           |
|                     |               | service_credentials.os_region_name. |                           |
|                     |               | Useful for multi-region deployments |                           |
|                     |               | where a service is shared between   |                           |
|                     |               | regions. E.g. RegionOne,RegionTwo   |                           |
+---------------------+---------------+-------------------------------------+---------------------------+

.. _individual-plugin-configuration:

Individual Plugin Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Individual plugins may also be configured in  ``searchlight.conf``.

.. note::

    Plugin configurations are typically named based on their resource type.
    The configuration name uses the following naming pattern:

    * The resource type name changed to all lower case

    * All ``::`` (colons) converted into ``_`` (underscores).

    For example: OS::Glance::Image --> [resource_plugin:os_glance_image]

To override a default configuration option on a specific plugin, you must
specify a configuration group for that plugin with the option(s) that you
want to override. For example, if you wanted to **just** disable the Glance
image plugin, you would add the following configuration group::

    [resource_plugin:os_glance_image]
    enabled = false

Each plugin may have additional configuration options specific to it.
Information about those configuration options will be found in documentation
for that plugin.

Finally, each integrated service (Glance, Nova, etc) may require
additional configuration settings. For example, typically, you will need
to add the ``searchlight_indexer`` notification topic to each service's
configuration in order for Searchlight to receive incremental updates from
that service.

.. note:: In Newton, notification messaging pools will become the default
          recommended configuration, which does not require changing any
          service configurations beyond enabling notifications.

          To enable the use of notification pools instead of a separate
          topic, add the ``notifications_pool`` option in the ``listener``
          section of ``searchlight.conf``. There is no need in this case
          to add an additional topic. Messages will begin to be delivered
          to the pool after ``searchlight-listener`` has started.

Please review each plugin's documentation for more information:

.. toctree::
   :maxdepth: 2
   :glob:

   ../admin/plugins/*
