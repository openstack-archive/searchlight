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

**********************
Designate Plugin Guide
**********************

Integration is provided via a plugin. There are multiple configuration
settings required for proper indexing and incremental updates. Some of the
settings are specified in Searchlight configuration files. Others are
provided in other service configuration files.

Searchlight Configuration
=========================

Searchlight resource configuration options are shown below with their
configuration file and default values. You only need to update the
below configuration options if you decide to change any options to
a non-default value.

See :ref:`searchlight-plugins` for default values and general configuration
information.

searchlight-api.conf
--------------------

Plugin: OS::Designate::Zone
^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_designate_zone]
    enabled = true
    index_name = searchlight

Plugin: OS::Designate::RecordSet
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_designate_recordset]
    enabled = true
    index_name = searchlight

.. warning::

    *OS::Designate::Zone* documents have a parent relationship to
    *OS::Designate::RecordSet* documents. Because of this you must have
    both *os_designate_zone* and *os_designate_recordset* plugin
    configurations enabled or disabled together and be set to the same
    index_name.

Designate Configuration
=======================

The Designate services must be configured properly to work with searchlight.

designate.conf
--------------

Notifications must be configured properly for searchlight to process
incremental updates. Use the following::

    notification_driver = messaging,searchlight_indexer
    rpc_backend = 'rabbit'

Restart designate-central, designate-pool-manager, designate-zone-manager and
you should be good to go!

local.conf (devstack)
---------------------

.. note::

    Designate resource types are *not* enabled by default (``enabled = false``)
    in the searchlight devstack script because designate is not
    installed by default in devstack.  You have two options for enabling
    designate resource types:

    1. Prior to stacking: modify the searchlight post config section in
       ``local.conf`` by adding a ``[[post-config|$SEARCHLIGHT_CONF]]`` section.

    2. After stacking: manually edit the ``searchlight-api.conf`` file.

The Designate plugin must be enabled and run with devstack to include Designate
with your devstack deployment. Follow the instructions here:
http://docs.openstack.org/developer/designate/devstack.html

Additionally, make sure to enable notifications in local.conf with the
following::

  DESIGNATE_NOTIFICATION_TOPICS=notifications,searchlight_indexer
  DESIGNATE_NOTIFICATION_DRIVER=messaging

Release Notes
=============

0.1.0.0 (Liberty)
-----------------

For best results, use the v2 Designate API. Using the Designate v1 API to
create domains results in the Designate service not sending all possible
status change notifications. This causes Designate record set documents to
stay in the ``Pending`` status in the search index.

The Horizon UI uses the v1 API and causes the above issue to be seen.
So in order to ensure the search index contains the correct status values
for record sets when using Horizon, you may set up a cron job to
re-index Designate data.

You should use the ``--no-delete`` option to prevent the index from
temporarily not containing any data (which otherwise would happen with a full
bulk indexing job)::

    searchlight-manage index sync --type OS::Designate::Zone,OS::Designate::RecordSet --force --no-delete

