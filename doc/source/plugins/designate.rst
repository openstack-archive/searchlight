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

Designate Configuration
=======================

Turn on Notifications::

Open designate.conf and make the following changes::

    notification_driver = messaging,searchlight_indexer
    rpc_backend = 'rabbit'

Restart designate-central, designate-pool-manager, designate-zone-manager and
you should be good to go!

Searchlight configuration
=========================

Designate-specific plugin configuration options are shown below with their
defaults values. You only need to specify the below configuration options if you
decide to change it to a non-default valuei; note that by default designate is
NOT enabled since it's not always installed::

    [resource_plugin:os_designate_zone]
    enabled = false
    index_name = searchlight

    [resource_plugin:os_designate_recordsets]
    enabled = false
    index_name = searchlight

.. warning::

    You need to have both *os_designate_zone* and *os_designate_recordset*
    enabled at this moment because of a relationship between them, and they
    must have the same index_name.
