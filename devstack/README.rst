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

================================
 Enabling Searchight in Devstack
================================

1. Download DevStack

2. Add this repo as an external repository::

     > cat local.conf
     [[local|localrc]]
     enable_plugin searchlight https://github.com/openstack/searchlight
     enable_service searchlight-api
     enable_service searchlight-listener

2. Customize searchlight configuration

To customize the searchlight configuration, add settings under the following
section in ``local.conf``::

    [[post-config|$SEARCHLIGHT_CONF]]

3. Add Plugin Configuration Hooks

The search service is driven using a plugin mechanism for integrating to other
services. Each integrated service may require additional configuration
settings. For example, typically, you will need to add the
``searchlight_indexer`` notification topic to each service's configuration.
Please review the plugins and add configuration appropriately.

.. toctree::
   :maxdepth: 1
   :glob:

   plugins/*

4. Run ``stack.sh``

.. note::
   This installs a headless JRE. If you are working on a desktop based OS
   (such as Ubuntu 14.04), this may cause tools like pycharms to no longer
   launch. You can switch between JREs and back: to a headed JRE version using:
   "sudo update-alternatives --config java".
