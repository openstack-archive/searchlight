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

*******************
Glance Plugin Guide
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

Plugin: OS::Glance::Image
^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_glance_image]
    enabled = true
    resource_group_name = searchlight

**Glance Image Property Protections**

Glance uses a property protections mechanism to ensure that certain
properties are limited to only people with the appropriate permissions.
Searchlight includes the same functionality and must be deployed with
the same property protections files and configured to use that file. A
sample configuration file is included in the repo and may be used for testing.

To configure it, add a ``property_protection_file`` property with a path
to the file in ``searchlight.conf``. For example::

    property_protection_file = /etc/searchlight/property-protections-roles.conf

See also: `Glance Property Protections <https://docs.openstack.org/glance/latest/admin/property-protections.html>`_

Plugin: OS::Glance::Metadef
^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_glance_metadef]
    enabled = true
    resource_group_name = searchlight

See also: `Metadata Definitions Catalog <https://docs.openstack.org/glance/latest/user/metadefs-concepts.html>`_

Glance Configuration
====================

The Glance services must be configured properly to work with searchlight.

glance-api.conf
---------------

Notifications must be configured properly for searchlight to process
incremental updates. Enable notifications using the following::

    [oslo_messaging_notifications]
    driver = messagingv2

.. note::

    Restart the Glance api service (g-api) after making changes.
    See :ref:`plugin_notifications` for more information on
    notification topics.

local.conf (devstack)
---------------------

The settings above may be automatically configured by ``stack.sh``
by adding them to the following post config section in devstack.
Just place the following in local.conf and copy the above settings
underneath it.::

    [[post-config|$GLANCE_API_CONF]]
    [DEFAULT]

Release Notes
=============

0.2.0.0 (Mitaka)
----------------

Notifications must be configured properly for searchlight to process
incremental updates. Searchlight must use its own topic. Use the following::

    notification_driver = messaging
    notification_topics = searchlight_indexer

0.1.0.0 (Liberty)
-----------------

Glance did not generate notifications for Image Member updates up to and
including the Liberty release.

This means that search results will include correct results when the image
visibility is ``public`` or ``private``, but ``shared`` images will only be
included in search results for the owning project without additional deployment
configuration.

The patch (https://review.openstack.org/221307) implements this feature and
will be included/merged in the Glance Mitaka release.

Searchlight developers/installers should apply the above patch in Glance when
using Searchlight with the Glance Liberty release.

Alternatively, you may set up a cron job to re-index glance images
periodically to get updated membership information.

You should use the ``--no-delete`` option to prevent the index from
temporarily not containing any data (which otherwise would happen with a full
bulk indexing job)::

    searchlight-manage index sync --type OS::Glance::Image --force --no-delete

