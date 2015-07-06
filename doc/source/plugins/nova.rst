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

Nova Configuration
==================

Turn on Notifications::

Open nova.conf and make the following changes::

    notification_driver = messaging
    notification_topics = searchlight_indexer
    rpc_backend = 'rabbit'
    notify_on_state_change=vm_and_task_state

Restart nova API and nova scheduler (n-api, n-sch).

Neutron Configuration
=====================

Since changes to Neutron can affect Nova instances you may optionally turn on
notifications for neutron.  If you do not, networking changes will only be
picked up by Searchlight when notifications are received from Nova.

Open neutron.conf and make the following changes::

    notification_driver = messaging
    notification_topics = searchlight_indexer
    rpc_backend = 'rabbit'

Restart neutron service (q-svc).
