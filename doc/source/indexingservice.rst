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
The search service determines the types of information that is searchable
via a plugin mechanism.  Within ``setup.cfg`` the setting within 
``[entry_points]`` named ``searchlight.index_backend``
should list the available indexable types. For example the entries to index
glance images and glance metadefs are::

    image = searchlight.elasticsearch.plugins.glance.images:ImageIndex
    metadef = searchlight.elasticsearch.plugins.glance.metadefs:MetadefIndex

Information about each of the plugins may be found here:

.. toctree::
   :maxdepth: 1
   :glob:

   plugins/*

Bulk indexing
-------------
To initially create the catalog index (or add to it later), run the
following command::

    $ searchlight-manage index sync

This will iterate through all registered search plugins and request that
they index all data that's available to them. This command may be re-run at
any time to perform a full re-index.

Incremental Updates
-------------------

Once a resource has been indexed, typically you will only need to consume
incremental updates rather than re-index the entire data set again.

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
