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

WARNING: The Swift plugin is currently EXPERIMENTAL as incremental indexing is
only provided via an experimental OSLO messaging middleware patch while
other indexing methodologies are explored for Swift.
See :ref:`proxy-server.conf` for additional information.

Integration is provided via a plugin. There are multiple configuration
settings required for proper indexing and incremental updates. Some of the
settings are specified in Searchlight configuration files. Others are
provided in Swift configuration files.

Swift Configuration
====================

reseller_admin_role
-------------------

Users with the Keystone role defined in `reseller_admin_role` (`ResellerAdmin`
by default) can operate on any account. The auth system sets the request
context variable `reseller_request` to True if a request is coming from a user
with this role.

Searchlight needs this role for its service user to access all of the swift
accounts during initial indexing. The `searchlight` user and `service` project
being referred to here are defined in the `service_credentials` section of
`searchlight.conf` file. If any of the Swift plugins are enabled, this
role must be added prior to running `searchlight-manage index sync`.

::

    openstack role add --user searchlight --project service ResellerAdmin


.. _proxy-server.conf:

proxy-server.conf
-----------------

Incremental indexing for searchlight is typically provided via OSLO
messaging. The Swift service currently doesn't send notifications, but
work has been started to investigate more performant ways to achieve
indexing.  In the meantime, experimental support for providing notifications
via middleware is provided in the following patch:

 * https://review.openstack.org/#/c/249471

 #. Apply the patch to the Swift proxy server
 #. Make the below configuration changes to `proxy-server.conf`
 #. Restart the Swift proxy server

::

    # Add the following new section
    [filter:oslomiddleware]
    paste.filter_factory = swift.common.middleware.oslo_notifications:filter_factory
    publisher_id = swift.localhost
    #Replace <user>,<password>,<rabbitip> and <rabbitport> for your environment values
    transport_url = rabbit://<user>:<password>@<rabbitip>:<rabbitport>/
    notification_driver = messaging
    notification_topics = notifications

    # Add oslomiddleware to pipeline:main
    # see example below.
    [pipeline:main]
    pipeline = catch_errors gatekeeper ...<other>... oslomiddleware proxy-logging proxy-server

.. note::

    Restart the swift proxy API service (s-proxy) after making changes.
    Starting in Newton, Searchlight can share the same notification topic as
    other services, because it uses a messaging pool.

Searchlight Configuration
=========================

Searchlight resource configuration options are shown below with their
configuration file and default values.

See :ref:`searchlight-plugins` for common options with their default values,
general configuration information, and an example complete configuration.

.. note::

    Unless you are changing to a non-default value, you do not need to
    specify any of the following configuration options. After enabling or
    disabling a plugin you do need to restart the searchlight services
    (`searchlight-api` and `searchlight-listener`).
    After enabling a Swift plugin, you will also need to run the sync job:
    `searchlight-manage index sync --type OS::Swift::Account`

searchlight.conf
----------------

Plugin: OS::Swift::Account
^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_swift_account]
    enabled = true
    resource_group_name = searchlight
    # Specify same value as in swift proxy-server.conf for reseller_prefix
    reseller_prefix = AUTH_

.. note::

    `os_swift_account` is disabled by default. You need to explicitly
    set enabled = True as shown above.

Plugin: OS::Swift::Container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_swift_container]
    enabled = true
    resource_group_name = searchlight

.. note::

    `os_swift_container` is disabled by default. You need to explicitly
    set enabled = True as shown above.

Plugin: OS::Swift::Object
^^^^^^^^^^^^^^^^^^^^^^^^^
::

    [resource_plugin:os_swift_object]
    enabled = true
    resource_group_name = searchlight

.. note::

    `os_swift_object` is disabled by default. You need to explicitly
    set enabled = True as shown above.


local.conf (devstack)
---------------------

At this time we recommend that you manually enable the Searchlight plugins
and middleware for Swift after devstack has completed stacking. Please
follow the instructions above.

Release Notes
=============

0.2.0.0 (Mitaka)
----------------

Notifications must be configured properly for searchlight to process
incremental updates. Searchlight must use its own topic. Use the following::

    notification_driver = messaging
    notification_topics = searchlight_indexer

Large scale swift cluster support is targeted at a future release, but
we encourage trial deployments to help us address issues as soon as possible.

Swift did not generate notifications for account/container/object CRUD
during the Mitaka release. This means that search results will not include
incremental updates after the initial indexing. However, there is a patch
available to enable notifications via oslo messaging for the Mitaka release.

* https://review.openstack.org/#/c/249471

For devstack, the easiest way to test is::

    cd /opt/stack/swift
    git review -x 249471
    <restart swift api>

Searchlight developers/installers should apply the above patch in Swift when
using Searchlight with the Swift Mitaka release. We are working with the
Swift team to create a supported incremental indexing methodology for future
releases.

Alternatively, you may set up a cron job to re-index swift
account/container/objects periodically to get updated information. The
recommendation is to use the notifications, because a full re-indexing will
not be performant in large installations.
::

    searchlight-manage index sync --type OS::Swift::Account

The Searchlight Swift plugin resource types follow the hierarchy similar to
Swift concepts
::

    OS::Swift:Account(Parent)
     -> OS:Swift::Container(Child)
       -> OS::Swift::Object(Grand Child)

which means indexing is initiated by specifying only the top parent
(OS::Swift::Account) and that will in-turn index all the child
plugins(Container and Object)

Searchlight is adding indexing isolation in the Newton release via a concept
called resource group isolation. This will better support re-indexing
scalability.

Additional properties can be similarly protected with the `admin_only_fields`
under each plugin's configuration section. Glob-like patterns are supported.
For instance::

    [resource_plugin:os_swift_object]
    admin_only_fields=x-meta-admin*
