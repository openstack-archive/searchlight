..
      Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
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

Searchlight Indexing
====================
In order for the Searchlight API service to return results, information
must be indexed. The two primary mechanisms by which this happens are indexing
from the source (which allows a complete index rebuild) and incrementally
updating the index based on information received via notifications.
The information indexed is determined by a plugin model.

Search plugins
--------------

The search service determines the type of information that is indexed and
searchable via a plugin mechanism.

See :ref:`searchlight-plugins` for plugin installation and general
configuration information.

See each plugin below for detailed information about specific plugins:

.. toctree::
   :maxdepth: 1
   :glob:

   plugins/*

Bulk indexing
-------------
To initially create the catalog index (or add new resource typs to it later),
run the following command::

    $ searchlight-manage index sync

This will iterate through all registered and enabled search plugins and
request that they perform a full indexing of all data that's available to them.

It is also possible to index just a single resource, or all resources
belonging to an index. For instance, to index all glance images::

    $ searchlight-manage index sync --type OS::Glance::Image

To index all resources in the 'searchlight' index::

    $ searchlight-manage index sync --index searchlight

You will be prompted to confirm unless ``--force`` is provided.

The ``searchlight-manage index sync`` command may be re-run at any time to
perform a full re-index of the data. This will delete the data, any mappings,
and recreate them from scratch, which means temporary data unavailability.
Zero downtime full re-indexing will be implemented in a future release.

For now, you may use the ``--no-delete`` option to update existing data and add
new data. This does have the side effect of leaving behind resource data that
may no longer exist in the source service, so should only be used as a
supplement for services that do not produce intermediate status change
notifications.

For example, in the Liberty release, the Glance service did not provide image
membership update notifications, even though it provided image update and
delete notifications. In order to provide accurate membership information, a
cron job could be set up with the following command to get the most up to date
information for indexed images::

    searchlight-manage index sync --type OS::Glance::Image --force --no-delete

Incremental Updates
-------------------

Once a resource has been indexed, typically you will only need to consume
incremental updates rather than re-index the entire data set again. The
preferred methodolgy is to set up notification listening.

Notifications
^^^^^^^^^^^^^
Many services publish notifications when there are changes to the resources
they own. The searchlight listener consumes these notifications and will
perform incremental updates to the index based on those notifications.

To start this service, run the following command::

    $ searchlight-listener

Note, this will typically require that you have configured notifications
properly for the service which owns the resource. For example, the glance
service owns images and metadata definitions. Please check the plugin
documentation for each service's specific configuration requirements.
