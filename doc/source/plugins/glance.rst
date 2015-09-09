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

Glance Configuration
====================

Turn on Notifications::

Open glance.api.conf and make the following changes::

    notification_driver = messaging
    rpc_backend = 'rabbit'
    notification_topics = notifications, searchlight_indexer

Restart glance API (g-api).

Searchlight Configuration
=========================

Glance uses a property protections mechanism to ensure that certain
properties are limited to only people with the appropriate permissions.
Searchlight includes the same functionality and must be deployed with
the same property protections files and configured to use that file. A
sample configuration file is included in the repo and may be used for testing.

To configure it::

Open the searchlight-api.conf file for editing (use editor of your choice)

::

  $ editor searchlight-api.conf

Suggested changes::

    property_protection_file = ~/openstack/searchlight/etc/property-protections-roles.conf

