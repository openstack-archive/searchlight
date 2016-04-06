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

Indexing model
--------------
The Mitaka Searchlight release introduced the ability to continue executing
search requests while reindexing operations are running. This feature is called
*zero-downtime reindexing*. In order to implement zero-downtime indexing, the
concept of a *resource group* was introduced.

A *resource group* is a collection of plugins that share an Elasticsearch
index.  Since each plugin represents a *resource type*, you can think of a
resource group as a collection of resource types.

For each resource group, Searchlight creates an index whose name consists of
the resource group name appended with a timestamp. Each resource group is
referred to by a pair of Elasticsearch aliases_. One alias is used for
searching by the API (the *search alias*), and the other (the *listener alias*)
is used to index incoming events.

During reindexing, a new index is created, and the listener alias is pointed at
both the old and new indices. Incoming events are therefore indexed into both
indices. The search alias is left pointing at the old index. Once indexing is
finished, both aliases are pointed solely at the new index and the old index
is deleted.

In order to improve the performance of reindexing, index refresh of the new
index is disabled during reindexing, and turned on after reindexing is done.
As a consequence, Documents synced to the new index are not searchable until
index is refreshed, but document retrieval by IDs still works, because GET
operation in Elasticsearch is realtime.

It is important to note that zero-downtime reindexing requires that **all**
plugins in a resource group are indexed together. When it's desired to index an
individual resource type, an optimization copies existing data directly from
the old index to the new one to avoid re-harvesting the data from each service
API.

.. note::
  Due to some limitations discovered during the Mitaka release, indexing into
  multiple indices (multiple plugin resource groups) is disabled. This behavior
  will be reimplemented in the Newton release, and potentially backported to
  the stable Mitaka release if possible.

.. _aliases: https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-aliases.html

Bulk indexing
-------------
To initially create the catalog index (or add new resource typs to it later),
run the following command::

    $ searchlight-manage index sync

This will iterate through all registered and enabled search plugins and
request that they perform a full indexing of all data that's available to them.

It is also possible to index just a single resource, or all resources
belonging to a resource group. For instance, to index all glance images::

    $ searchlight-manage index sync --type OS::Glance::Image

As described above, this will create a new index for all plugins that share a
resource group with OS::Glance::Image. The management command will retrieve
up-to-date information from the Glance API. Data for other plugins will be
bulk-copied from a preexisting index into the new one using the scroll_ and
bulk_ features of Elasticsearch.

To index all resources in the 'searchlight' resource group::

    $ searchlight-manage index sync --index searchlight

You will be prompted to confirm unless ``--force`` is provided.

The ``searchlight-manage index sync`` command may be re-run at any time to
perform a full re-index of the data. As described above, there should be no
or very little impact on search requests during this process.

.. _scroll: https://www.elastic.co/guide/en/elasticsearch/reference/current/search-request-scroll.html
.. _bulk: https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html

Parent/child relationships
--------------------------
Some plugins contain multiple resources with parent/child relationships;
the Designate plugins are an example. Because reindexing parent data independent
of child documents does not logically make sense (without orphaning them), it
is not possible to request indexing of a child resource type::

    $ searchlight-manage index sync --type OS::Designate::RecordSet

    'OS::Designate::RecordSet' is a child of 'OS::Designate::Zone' and cannot be indexed separately.
    Indexing 'OS::Designate::Zone' will re-index all child resource types.

You can see parent/child relationships in the list of resources presented prior
to indexing::

    $ searchlight-manage index sync --type OS::Designate::Zone

    Resource types (and indices) matching selection:
      OS::Designate::Zone (designate)
          ---->  OS::Designate::RecordSet

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
