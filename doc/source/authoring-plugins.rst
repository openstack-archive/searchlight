..
      Copyright 2016 Hewlett-Packard Enterprise Development Company, L.P.
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

.. _searchlight-plugin-authoring:

Authoring Searchlight Plugins
=============================

At a bare minimum, a plugin must consist of an elasticsearch mapping, and a
method by which it can provide data to be indexed. Many plugins also require a
way to receive updates in order to keep the index up to date. For Openstack
resources, typically the service API is used for initial indexing and
notifications are received via oslo.messaging.

This documentation will use as an example the Nova Server plugin.

File structure
--------------
Plugins live in ``searchlight/elasticsearch/plugins``. We have tended to create
a subpackage named after the service (``nova``) and within it a module named
after the resource type (``server.py``). Notification handlers can be in a file
specific to each resource type but can also be in a single file together
(existing ones use ``notification_handlers.py``).

``server.py`` contains a class named ``ServerIndex`` that implements the base
class ``IndexBase`` found in ``searchlight.elasticsearch.plugins.base``.

.. note::
   
    If there are plugins for multiple resources within the same Openstack
    service (for example, Glance images and meta definitions) those plugins
    can exist in the same subpackage ('glance') in different modules, each
    implementing an IndexBase.

Enabling plugins
----------------
Searchlight plugins are loaded by Stevedore_. In order for a plugin to be
enabled for indexing and searching, it's necessary to add an entry to the
``entry_points`` list in Searchlight's configuration in ``setup.cfg``. The
name should be the plugin resource name (typically the name used to represent
it in Heat_)::

    [entry_points]
    searchlight.index_backend = 
        os_nova_server = searchlight.elasticsearch.plugins.nova.servers:ServerIndex

.. _Stevedore: http://docs.openstack.org/developer/stevedore/
.. _Heat: http://docs.openstack.org/developer/heat/template_guide/openstack.html

Required functions
------------------

Document type
^^^^^^^^^^^^^
As a convention, plugins define their document type (which will map to an
ElasticSearch document type) as the resource name Heat uses to identify it::

    @classmethod
    def get_document_type(self):
        return "OS::Nova::Server"

Retrieving object for initial indexing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Plugins must implement ``get_objects`` which in many cases will go to the
API of the service it"s indexing. It should return an iterable that will be
passed to a function (also required) named ``serialize``, which in turn must
return a dictionary suitable for Elasticsearch to index.

Mapping
^^^^^^^

``get_mapping`` is also required. It must return a dictionary that tells
Elasticsearch how to map documents for the plugin (see the documentation for
mapping_).

At a minimum a plugin should define an ``id`` field and an ``updated_at`` field
because consumers will generally rely on those being present; a ``name`` field
is highly advisable. If the resource doesn"t contain these values your
``serialize`` function can map to them. In particular, if your resource does
not have a native ``id`` value, you must override ``get_document_id_field`` to
so that the indexing code can retrieve the correct value when indexing.

It is worth understanding how Elasticsearch indexes various field types,
particularly strings. String fields are typically broken down into tokens to
allow searching::

  "The quick brown fox" -> ["The", "quick", "brown", "fox"]

This works well for full-text type documents but less well, for example,
for UUIDS::

  "aaab-bbbb-55555555" -> ["aaab", "bbbb", "55555555"]

In the second example, a search for the full UUID will not match. As a result,
we tend to mark these kinds of fields as ``not_analyzed`` as with the example
to follow.

Where field types are not specified, Elasticsearch will make a best guess from
the first document that's indexed.

Some notes (expressed below as comments starting with #)::

    {
      # This allows indexing of fields not specified in the mapping doc
      "dynamic": true,
      "properties": {

        # not_analyzed is important for id fields; it prevents Elasticsearch
        # tokenizing the field, allowing for exact matches
        "id": {"type": "string", "index": "not_analyzed"},

        # This allows name to be tokenized for searching, but Searchlight will
        # attempt to use the 'raw' (untokenized) field for sorting which gives
        # more consistent results
        "name": {
          "type": "string",
          "fields": {
            "raw": {"type": "string", "index": "not_analyzed"}
          }
        }
      }
    }

Doc values
**********
For many field types Searchlight will alter the mapping to change the format in
which field data is stored. Prior to Elasticsearch 2.x field values by default
were stored in 'fielddata' format, which could result in high memory usage under
some sort and aggregation operations. An alternative format, called ``doc_values``
trades slightly increased disk usage for better memory efficiency. In Elasticsearch
2.x ``doc_values`` is the default, and Searchlight uses this option as the default
regardless of Elasticsearch version. For more information see the Elasticsearch
documentation_.

.. _documentation: https://www.elastic.co/guide/en/elasticsearch/guide/current/doc-values.html

Generally this default will be fine. However, there are several ways in which
the default can be overriden:

* Globally in plugin configuration; in ``searchlight.conf``::

    [resource_plugin]
    mapping_use_doc_values = false

* For an individual plugin in ``searchlight.conf``::

    [resource_plugin:os_nova_server]
    mapping_use_doc_values = false

* For a plugin's entire mapping; in code, override the ``disable_doc_values``
  property::

    @property
    def disable_doc_values(self):
        return False

* For individual fields in a mapping, by setting ``doc_values`` to False::

    {
      "properties": {
        "some_field": {"type": "date", "doc_values": False}
      }
    }

Access control
^^^^^^^^^^^^^^
Plugins must define how they are access controlled. Typically this is a
restriction matching the user's project/tenant::

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

Any filters listed will be applied to queries against the plugin's document
type, but only for non-administrative users.

Faceting
^^^^^^^^
Any fields defined in the mapping document are eligible to be identified as
facets, which allows a UI to let users search on specific fields. Many plugins
define ``facets_excluded`` which exclude specified fields. Many also define
``facets_with_options`` which should return fields with low cardinality where
it makes sense to return valid options for those fields.

Protected fields
^^^^^^^^^^^^^^^^
``admin_only_fields`` determines fields which only administrators should be
able to see or search. For instance, this will mark any fields beginning with
``OS-EXT-SRV-ATTR:`` as well as any defined in the plugin configuration::

    @property
    def admin_only_fields(self):
        from_conf = super(ServerIndex, self).admin_only_fields
        return ['OS-EXT-SRV-ATTR:*'] + from_conf

These fields end up getting indexed in separate admin-only documents.

Parent/child relationships
--------------------------
In some cases there is a strong ownership implied between plugins. In these
cases the child plugin can define ``parent_plugin_type`` and
``get_parent_id_field`` (which determines a field on the child that refers
to its parent). See the Designate RecordSet plugin for an example.

Remember that Elasticsearch is not a relational database and it doesn't do
joins, per se, but this linkage does allow running queries referencing children
(or parents).

.. _mapping: https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html
