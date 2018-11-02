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

.. _Indexing-Model:

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
  multiple indices (multiple plugin resource groups) is disabled. The newton release
  implemented full support for specifying different resource groups for different
  resource types.

.. _using-resource-groups:

Sorting across resource groups
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Using multiple resource groups will impact sort behavior when sorting on fields
across resource types when all the resource types don't have the requested 'sort-by field'.
Follow the guidelines below to avoid errors:

  https://www.elastic.co/guide/en/elasticsearch/reference/current/search-request-sort.html#_ignoring_unmapped_fields
  https://www.elastic.co/guide/en/elasticsearch/reference/current/search-request-sort.html#_missing_values

.. _aliases: https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-aliases.html

.. _ES-Bulk-Indexing:

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

You can use the wildcard character * at the *end* of the ``type`` argument.
For instance, the following will match all cinder plugins::

    $ searchlight-manage index sync --type OS::Cinder::*

Wildcard characters are only allowed at the end of the argument; they will not
be matched anywhere else.

To index all resources in the 'searchlight' resource group::

    $ searchlight-manage index sync --index searchlight

You will be prompted to confirm unless ``--force`` is provided.

To reindex resources only without notification::

    $ searchlight-manage index sync --notification-less

.. note::

    We *strongly* recommend putting the notification-less plugins in their own
    resource group and scheduling a cron_
    job to periodically re-sync the notification plugins to keep the documents
    up to date.

The ``searchlight-manage index sync`` command may be re-run at any time to
perform a full re-index of the data. As described above, there should be no
or very little impact on search requests during this process.

.. _scroll: https://www.elastic.co/guide/en/elasticsearch/reference/current/search-request-scroll.html
.. _bulk: https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html
.. _cron: https://en.wikipedia.org/wiki/Cron

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

Child plugins will inherit their resource group name from their parent. Any
child configuration setting for resource_group_name will be ignored.

Incremental Updates
-------------------

Once a resource has been indexed, typically you will only need to consume
incremental updates rather than re-index the entire data set again. The
preferred methodology is to set up notification listening.

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

Multi-Thread Support
--------------------
The Newton Searchlight release introduced multiple thread support for
indexing. Previously when the ``searchlight-manage index sync``
command was executed, all indexing occurred in a single thread. To boost
the performance of the indexing functionality, each resource type
will now index in its own thread. Multiple indexing threads will run
concurrently.

By default, the maximum number of simultaneous threads is 3. This limit
can be modified in the Searchlight configuration file. The setting is
called ``workers`` and lives under ``[manage]``. For example, to
increase the maximum number of threads to 6, the following can be added
to the Searchlight configuration file::

    [manage]
    workers=6

The use of threads can also affect the parsing of the log files. The
default formatting of the log messages include only the process ID,
but no thread-specific information. This can be changed by modifying
the formatting string settings in the Searchlight configuration file.
To add the thread ID for a message, add ``%(thread)d``. To add the thread
name, add ``%(threadName)s``. For example, to add the thread ID and the
thread name after the process ID to the logging message, the following
setting can be added to the Searchlight configuration file::

    logging_default_format_string = %(asctime)s.%(msecs)03d %(process)d %(thread)d %(threadName)s %(levelname)s %(name)s [-] %(instance)s%(message)s

Force Elasticsearch indexing
----------------------------
The Newton Searchlight release introduced the ability to reindex
from Elasticsearch only, bypassing the plugin APIs altogether.
This option is useful if there has been a change to the mapping
definitions or the index settings. This functionality is enabled
with the option ``--apply-mapping-changes`` for the ``index`` command.

A sample usage would be::

    $ searchlight-manage index aliases --apply-mapping-changes

The ``--type`` option is not compatible with the ``--apply-mapping-changes``
option. Specifying both options on the command line will result in an error.

.. warning::

    The resource group cannot be changed when using this option.
    If you do change the resource group, the underlying index will
    be changed and will result in an empty index.

.. _ES-Index-Cleanup:

Elasticsearch Index Cleanup
---------------------------

In some cases, there may be orphaned Searchlight indices in Elasticsearch.
An orphaned index is one that is no longer used by Searchlight, either
directly or through an alias.

To help detect which Searchlight-related indices may be orphaned in
Elasticsearch, the ``searchlight-manage`` command will display all indices
that are currently being used by Searchlight. This is the ``aliases``
option to the ``index`` command::

    $ searchlight-manage index aliases

This command outputs a listing of all indices that are used by
Searchlight (based on the current configuration file). The aliases
associated with each index is also shown. A sample output will look
like this::

    $ searchlight-manage index aliases
    List of Elasticsearch indices (and their associated aliases) used by Searchlight.

    Note:
    The indices are based on the current config file.
    To view indices used by other Searchlight config files, use the --config-file option.

    Indices are denoted with a '*'
    Aliases are denoted with a '+'

        * searchlight-2016_07_13_17_09_27
            + searchlight-listener
            + searchlight-search
        * sl-swift-2016_07_13_17_09_26
            + sl-swift-listener
            + sl-swift-search

The example shows that Searchlight is using two indices in Elasticsearch:
``searchlight-2016_07_13_17_09_27`` and ``sl-swift-2016_07_13_17_09_26``.
The index ``searchlight-2016_07_13_17_09_27`` has two aliases: ``searchlight-listener``
and ``searchlight-search``. The index ``sl-swift-2016_07_13_17_09_26`` has
two aliases: ``sl-swift-listener`` and ``sl-swift-search``.

Any other indices or aliases in Elasticsearch are not used by this specific
Searchlight configuration. NOTE: If there are other Searchlight
instances running with a different configuration, their indices and aliases
will not be displayed by this command. The user will need to rerun the
``index aliases`` command using other configuration files.

.. _Notifications:

Notifications
=============
Aside from periodic reindexing, Searchlight can index in close to real-time
by subscribing to oslo.messaging notifications_. To configure services to send
them, it's typically only necessary to enable a driver in their configuration
files::

  [oslo_messaging_notifications]
  driver = messaging

Most notifications are emitted by a service's API but some services also emit
them in scheduler or conductor components.

Searchlight subscribes to notifications using a listener pool_ so it will not
steal notifications from e.g. telemetry projects.

.. _oslo-notifications: https://wiki.openstack.org/wiki/Oslo/Messaging#Emitting_Notifications
.. _pool: https://specs.openstack.org/openstack/oslo-specs/specs/kilo/notification-listener-pools.html

RabbitMQ
--------
The rabbitmq driver is the most commonly used. The permissions_ required for
searchlight are::

* configure: '^(searchlight-listener|openstack|nova|neutron|cinder|glance)$'
* write: '^(searchlight-listener)$'
* read: '^(searchlight-listener|nova|glance|cinder|neutron|openstack)$'

.. _permissions: https://www.rabbitmq.com/access-control.html
