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
disabled, enabled and configured in the ``searchlight-api.conf`` file.

Configuring Plugins
-------------------

After installation, plugins are configured in ``searchlight-api.conf``.

Default Plugin Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

All plugins inherit their configuration from a default configuration group of
``[resource_plugin:default]`` in ``searchlight-api.conf``. For example::

    [resource_plugin:default]
    enabled = true
    index_name = searchlight

The below table shows the available default configuration options. It is only
necessary to specify a configuration option in ``searchlight-api.conf`` if
you want to use a value other than the default value specified below.

+--------------------+---------------+-------------------------------------+---------------------------+
| Option             | Default value | Description                         | Action(s) Required        |
+====================+===============+=====================================+===========================+
| enabled            | true          | An installed plugin may be enabled  | | Restart services        |
|                    |               | or disabled. When disabled, it will | | Re-index affected types |
|                    |               | not be available for bulk indexing, |                           |
|                    |               | notification listening, or          |                           |
|                    |               | searching.                          |                           |
+--------------------+---------------+-------------------------------------+---------------------------+
| index_name         | searchlight   | The ElasticSearch index where the   | | Restart services        |
|                    |               | plugin resource documents will be   | | Re-index affected types |
|                    |               | stored in. It is recommended to not |                           |
|                    |               | change this unlesss needed.         |                           |
+--------------------+---------------+-------------------------------------+---------------------------+

.. note::

    After making changes to ``searchlight-api.conf`` you must perform the
    actions indicated in the table. Action notes:

    1. ``Restart services``: Restart all running ``searchlight-api`` *and*
       ``searchlight-listener`` processes.

    2. ``Re-index affected types``: You will need to re-index any resource
       types affected by the change. (See :doc:`indexingservice`).

Individual Plugin Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Individual plugins may also be configured in  ``searchlight-api.conf``.

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

Please review each plugin's documentation for more information:

.. toctree::
   :maxdepth: 1
   :glob:

   plugins/*
