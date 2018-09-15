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


Installing and Configuring Elasticsearch
========================================

The Searchlight indexing service is responsible for indexing data in
Elasticsearch [1]_; Elasticsearch has very good documentation on
installation but some pointers are provided here.

.. IMPORTANT:: We *strongly* recommend using ElasticSearch 5.x and the
   accompanying python client version [2]_. ElasticSearch 2.x is still
   supported and will be removed after Stein cycle.

Installation
~~~~~~~~~~~~

Elasticsearch requires a Java Runtime Environment (or Java Development Kit). OpenJDK
and Oracle's Java are supported. Information on the current recommended version can
be found in the installation instructions [3]_.

Installing from a download package
##################################

Links to various formats and also older versions of Elasticsearch can be found
on the download page [4]_. Once downloaded and extracted, you can start
Elasticsearch with:

.. code-block:: console

    bin/elasticsearch

For more details see the installation instructions [5]_

Quick command line example with 5.6.11:

.. note::

    Do the following commands as "root" or via sudo <command>

Download the ES package:

.. code-block:: console

    cd ~
    wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-5.6.11.deb
    sudo dpkg -i elasticsearch-5.6.11.deb
    sudo update-rc.d elasticsearch defaults 95 10
    sudo /etc/init.d/elasticsearch start

.. note::

    If you install ElasticSearch 5.x, You should install
    python-elasticsearch>=5.0.0. global-requirements currently constrains it to v2.x

Configuration
~~~~~~~~~~~~~

Elasticsearch comes with very a very sensible default configuration that
allows for clustering and high performance out of the box. There are some
settings, both general and specific to Searchlight's indexing service, that might
be of interest depending on your scenario.

Elasticsearch's configuration is in $ES_HOME/config/elasticsearch.yaml, where
ES_HOME is the directory in which Elasticsearch is installed. It uses YAML,
a superset of JSON.

Indices
#######

Elasticsearch (and Lucene) store information in indices. Within an index can
be one or more document types. Searchlight's indexing service uses an index
per service that has a plugin available, and each plugin generally will have
its own document type. For instance, the glance plugin has *glance.image* and
*glance.metadef*. Since the volume of data is lower than a typical use case for
Elasticsearch it may make sense to change the default sharing and replication
mechanism. We also recommend disabling implicit index creation, though if you
are sharing an Elasticsearch installation this may be inadvisable. The
following options control indexing behavior:

.. code-block:: yaml

    # Number of shards for each index (performance)
    index.number_of_shards: 5
    # Number of replicas per shard (redundancy and recovering)
    index.number_of_replicas: 1

    # Disable automatic index creation so that index creation
    # is an explicit action
    action.auto_create_index: false

Index settings
**************

In addition to server-wide index settings it's possible to configure
Searchlight to apply settings to indices it creates with
``searchlight-manage``. Index settings can be specified as follows in
``searchlight.conf``:

.. code-block:: yaml

    [elasticsearch]
    index_settings = refresh_interval:2s,number_of_replicas:1

The ``index.`` prefix for settings is optional; Searchlight will prepend it if
it's not given (e.g. ``index.refresh_interval`` is also acceptable).

Index settings are applied at creation time and so are not limited to the
'dynamic' index settings. They are applied to all indices at the time they
are created. If you wish to update settings for an existing index, you
should use the Elasticsearch API to do so or reindex.

See also [9]_, [10]_.

Scripts
#######

The scripting module allows to use scripts in order to evaluate custom
expressions. Scripting is turned off by default in elasticsearch latest
versions. Searchlight doesn't allow scripts in the search api but requires
scripts to sync Index updates from notifications. For security purpose index
updates are allowed only for admin role.

.. code-block:: yaml

    script.engine.groovy.inline.update: on

See also [8]_.

Development
###########

For development, Elasticsearch's default configuration is overkill. It's
possible to run Elasticsearch with a much lower memory footprint than by
default, and you may wish to disable clustering behavior.

.. code-block:: yaml

    # Configures elasticsearch as a single node (no discovery)
    node.local: true

    # Disable sharding and replication
    index.number_of_shards: 1
    index.number_of_replicas: 0

JVM settings
************

Setting the ES_HEAP_SIZE environment variable will restrict how much memory
Elasticsearch uses, equivalent to setting -Xmx and -Xms to the same value for
the Java runtime. For development you can set it as low as a few tens of MB:

.. code-block:: console

    export ES_HEAP_SIZE=40m

Memory usage will be somewhat higher than that figure, because Java itself
requires memory on top of that.

Production
##########

Some settings you may wish to change for production:

.. code-block:: yaml

    # Cluster name is used by cluster discovery; it's important to ensure
    # this is set across all nodes you wish to be in the cluster
    cluster.name: searchlight

    # By default elasticsearch picks a random name from a list of Marvel
    # comic characters. If you specify this, make sure it's different on
    # each node in the cluster
    node.name: This Node Name

    # Bind to a non-standard address
    network.host: 0.0.0.0

    # Bind to a non-standard port
    http.port: 9200

    # Configure the default data and log directories. By default, these
    # directories will be created in $ES_HOME.
    path:
      logs: /var/log/elasticsearch
      data: /var/data/elasticsearch

    # This setting locks the Elasticsearch process address space into RAM
    # (preventing locking). If you set this, ensure that you've configured
    # ES_HEAP_SIZE appropriately (see below). Linux only.
    bootstrap.mlockall: true

For more details see Elasticsearch's configuration information [6]_.

Specifying nodes in a cluster
*****************************

Elasticsearch's default discovery relies on multicast requests. If this isn't
a good fit, you can use unicast discovery:

.. code-block:: yaml

    discovery.zen.ping.multicast.enabled: false
    discovery.zen.ping.unicast.hosts: ['w.x.y.z', 'w.x.y.z']


See [7]_ for more details.

JVM settings
************

For production, Elasticsearch recommends setting the ES_HEAP_SIZE environment
variable to a value around 60% of a dedicated machine's memory:

.. code-block:: yaml

    export ES_HEAP_SIZE=2g


References
~~~~~~~~~~

.. [1] https://www.elastic.co/
.. [2] https://elasticsearch-py.readthedocs.io/en/master/#compatibility
.. [3] https://www.elastic.co/guide/en/elasticsearch/reference/current/setup.html
.. [4] https://www.elastic.co/downloads/elasticsearch
.. [5] https://www.elastic.co/guide/en/elasticsearch/reference/current/install-elasticsearch.html
.. [6] https://www.elastic.co/guide/en/elasticsearch/reference/current/settings.html
.. [7] https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-discovery-zen.html
.. [8] https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-scripting.html#modules-scripting
.. [9] https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index\_.html
.. [10] https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-update-settings.html
