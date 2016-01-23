..
    (c) Copyright 2016 Hewlett-Packard Development Company, L.P.

    Licensed under the Apache License, Version 2.0 (the "License"); you may
    not use this file except in compliance with the License. You may obtain
    a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
    License for the specific language governing permissions and limitations
    under the License.

******************
Swift Plugin Guide
******************

WARNING: Swift plugin is currently EXPERIMENTAL as notifications aren't
fully supported. See below on enabling notifications.

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

Plugin: OS::Swift::Account
^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_swift_account]
    enabled = true
    index_name = searchlight
    #Specify same value as in swift proxy config for reseller_prefix
    reseller_prefix = AUTH_

.. note::

    os_swift_account is disabled by default. You need to explicitly set enabled = True as shown above

Plugin: OS::Swift::Container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_swift_container]
    enabled = true
    index_name = searchlight

.. note::

    os_swift_container is disabled by default. You need to explicitly set enabled = True as shown above

Plugin: OS::Swift::Object
^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_swift_object]
    enabled = true
    index_name = searchlight

.. note::

    os_swift_object is disabled by default. You need to explicitly set enabled = True as shown above

Swift Configuration
====================

The Swift service currently doesn't send notifications.
Apply this patch https://review.openstack.org/#/c/249471
for adding notification middleware to swift.

reseller_admin_role
-------------------

Users with the Keystone role defined in reseller_admin_role (ResellerAdmin by default)
can operate on any account. The auth system sets the request environ reseller_request
to True if a request is coming from a user with this role.

Searchlight needs this role for its service user to access all the swift accounts
for initial indexing. The searchlight user and sevice project being referred here is the
one defined in service_credentials section of searchlight conf file.

::

    openstack role add --user searchlight --project service ResellerAdmin


proxy-server.conf
-----------------

Notifications must be configured properly for searchlight to process
incremental updates. Use the following::

    #Add the following new section
    [filter:oslomiddleware]
    paste.filter_factory = swift.common.middleware.oslo_notifications:filter_factory
    publisher_id = swift.localhost
    #Replace <user>,<password>,<rabbitip> and <rabbitport> for your environment values
    transport_url = rabbit://<user>:<password>@<rabbitip>:<rabbitport>/
    notification_driver = messaging
    notification_topics = searchlight_indexer

    #Add oslomiddleware to pipeline:main see example below.
    [pipeline:main]
    pipeline = catch_errors gatekeeper healthcheck ... oslomiddleware proxy-logging  proxy-server


.. note::

    Restart swift proxy API service (s-proxy) after making changes.

local.conf (devstack)
---------------------

The settings above may be automatically configured by ``stack.sh``
by adding them to the following post config section in devstack.
Just place the following in local.conf and copy the above settings
underneath it.::

    [[post-config|$SWIFT_PROXY_CONF]]
    [DEFAULT]

Release Notes
=============

0.2.0.0 (Mitaka)
----------------

Swift did not generate notifications for account/container/object CRUD

This means that search results will not include incremental updates after
the initial indexing.

The patch (https://review.openstack.org/#/c/249471) implements this feature.

For devstack, the easiest way to test is
cd /opt/stack/swift
git review -x 249471

Searchlight developers/installers should apply the above patch in Swift when
using Searchlight with the Swift Mitaka release.

Alternatively, you may set up a cron job to re-index swift
account/container/objects periodically to get updated information. The
recommendation is to use the notifications.

You should use the ``--no-delete`` option to prevent the index from
temporarily not containing any data (which otherwise would happen with a full
bulk indexing job)::

    searchlight-manage index sync --type OS::Swift::Account --force --no-delete

Searchlight swift plugin resource types follow the hierarchy similar to
Swift concepts

    OS::Swift:Acccount(Parent)
     -> OS:Swift::Container(Child)
       -> OS::Swift::Object(Grand Child)

which means indexing is initiated by specifying only the top parent
(OS::Swift::Account) and that will in-turn index all the child
plugins(Container and Object)

