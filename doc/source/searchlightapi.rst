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

Searchlight API
===============

Searchlight's API adds authentication and Role Based Access Control in front
of Elasticsearch's query API.

Authentication
--------------

Searchlight, like other OpenStack APIs, depends on Keystone and the
OpenStack Identity API to handle authentication. You must obtain an
authentication token from Keystone and pass it to Searchlight in API requests
with the ``X-Auth-Token`` header.

See :doc:`authentication` for more information on integrating with Keystone.

Using v1
--------

For the purposes of examples, assume a Searchlight server is running
at the URL ``http://searchlight.example.com`` on HTTP port 80. All
queries are assumed to include an ``X-Auth-Token`` header. Where request
bodies are present, it is assumed that an appropriate ``Content-Type``
header is present (usually ``application/json``).

Searches use Elasticsearch's
`query DSL <http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/query-dsl.html>`_.

Elasticsearch stores each 'document' in an 'index', which has one or more
'types'. Searchlight's indexing service stores all resource
types in their own document type, grouped by service into indices. For
instance, the ``OS::Glance::Image`` and ``OS::Glance::Metadef`` types both
reside in the ``searchlight`` index. ``type`` is unique to a resource type.

Document access is defined by each document type, for instance for glance
images:

* If the current user is the resource owner OR
* If the resource is marked public

Some resources may have additional rules. Administrators have access to all resources.

Querying available plugins
~~~~~~~~~~~~~~~~~~~~~~~~~~

Searchlight indexes OpenStack resources as defined by installed plugins. In
general, a plugin maps directly to an OpenStack resource type. For instance, a
plugin might index nova instances, or glance images. There may be multiple
plugins related to a given OpenStack project (an example being glance images
and metadefs).

A given deployment may not necessarily expose all available plugins.
Searchlight provides a REST endpoint to request a list of installed plugins.
A ``GET`` request to  ``http://searchlight.example.com/v1/search/plugins``
might yield::

    {
        "plugins": [
            {
                 "name": "OS::Glance::Image",
                 "type": "OS::Glance::Image",
                 "index": "searchlight"
            },
            {
                 "name": "OS::Glance::Metadef",
                 "type": "OS::Glance::Metadef",
                 "index": "searchlight"
            }

        ]
    }

This represents Glance image and metadef resources indexed in the same
Elasticsearch ``index`` and a ``type`` specific to the resource. To view
all indexed Glance images in Elasticsearch directly, rather than in Searchlight
(assuming a server running on localhost) would therefore be a request such as::

    curl http://localhost:9200/searchlight/OS::Glance::Image/_search

Running a search
~~~~~~~~~~~~~~~~

The simplest query is to ask for everything we have access to. We issue a
``POST`` request to ``http://searchlight.example.com/v1/search`` with the
following body::

    {
        "query": {
            "match_all": {}
        }
    }

The data is returned as a JSON-encoded mapping from Elasticsearch::

  {
    "_shards": {
      "failed": 0,
      "successful": 2,
      "total": 2
    },
    "hits": {
      "hits": [
        {
          "_id": "76580e9d-f83d-49d8-b428-1fb90c5d8e95",
          "_index": "searchlight",
          "_type": "OS::Glance::Image"
          "_score": 1.0,
          "_source": {
            "id": "76580e9d-f83d-49d8-b428-1fb90c5d8e95",
            "members": [],
            "name": "cirros-0.3.2-x86_64-uec",
            "owner": "d95b27da6e9f4acc9a8031918e443e04",
            "visibility": "public",
            ...
          }
        },
        {
          "_id": "OS::Software::DBMS",
          "_index": "searchlight",
          "_type": "metadef",
          "_score": 1.0,
          "_source": {
            "description": "A database is an ...",
            "display_name": "Database Software",
            "namespace": "OS::Software::DBMS",
            "objects": [
              {
                "description": "PostgreSQL, often simply 'Postgres' ...",
                "name": "PostgreSQL",
                "properties": [
                  {
                    "default": "5432",
                    "description": "Specifies the TCP/IP port...",
                    "property": "sw_database_postgresql_listen_port",
                    ...
                  },
                  ...
                ]
              }
            ],
            "tags": [
              {
                "name": "Database"
              },
            ]
          }
        },
        ...
      ],
      "max_score": 1.0,
      "total": 8
    },
    "timed_out": false,
    "took": 1
  }

Each ``hit`` is a document in Elasticsearch, representing an OpenStack
resource. the fields in the root of each hit are:

* ``_id``

  Uniquely identifies the resource within its OpenStack context (for
  instance, Glance images use their GUID).

* ``_index``

  The service to which the resource belongs (e.g. ``searchlight``).

* ``_type``

  The document type within the service (e.g. ``image``, ``metadef``)

* ``_score``

  Where applicable the relevancy of a given ``hit``. By default,
  the field upon which results are sorted.

* ``_source``

  The document originally indexed. The ``_source`` is a map, where each key
  is a ``field`` whose value may be a scalar value, a list, a nested object
  or a list of nested objects.

More example searches
~~~~~~~~~~~~~~~~~~~~~

Results are shown here only where it would help illustrate the example. The
``query`` parameter supports anything that Elasticsearch exposes via its
`query DSL <http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/query-dsl-queries.html>`_.
There are normally multiple ways to represent the same query, often with some
subtle differences, but some common examples are shown here.

Restricting document index or type
**********************************
To restrict a query to Glance image and metadef information only (both
``index`` and ``type`` can be arrays or a single string)::

    {
        "query": {
            "match_all": {}
        },
        "type": ["OS::Glance::Image", "OS::Glance::Metadefs"]
    }

If ``index`` or ``type`` are not provided they will default to covering as
wide a range of results as possible. Be aware that it is possible to specify
combinations of ``index`` and ``type`` that can return no results. In general
``type`` is preferred since ``type`` is unique to a resource.

Retrieving an item by id
************************
To retrieve a resource by its OpenStack ID (e.g. a glance image), we can use
Elasticsearch's `term query <http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/query-dsl-term-query.html>`_::

  {
    "index": "searchlight",
    "query": {
      "term": {
        "id": "79fa243d-e05d-4848-8a9e-27a01e83ceba"
      }
    }
  }

Limiting the fields returned
****************************
To restrict the ``source`` to include only certain fields::

  {
    "type": "OS::Glance::Image",
    "fields": ["name", "size"]
  }

Gives::

  {
    "_shards": {
      "failed": 0,
      "successful": 1,
      "total": 1
    },
    "hits": {
      "hits": [
        {
          "_id": "76580e9d-f83d-49d8-b428-1fb90c5d8e95",
          "_index": "searchlight",
          "_score": 1.0,
          "_source": {
            "name": "cirros-0.3.2-x86_64-uec",
            "size": 3723817
          },
          "_type": "OS::Glance::Image"
        },
        ...
      ],
      "max_score": 1.0,
      "total": 4
    },
    "timed_out": false,
    "took": 1
  }

Sorting
*******
Elasticsearch allows sorting by single or multiple fields. See Elasticsearch's
`sort <https://www.elastic.co/guide/en/elasticsearch/reference/current/search-request-sort.html>`_
documentation for details of the allowed syntax. Sort fields can be included as a top
level field in the request body. For instance::

  {
    "query": {"match_all": {}},
    "sort": {"name": "desc"}
  }

You will see in the search results a ``sort`` field for each result::

  ...
  {
     "_id": "7741fbcc-3fa9-4ace-adff-593304b6e629",
     "_index": "glance",
     "_score": null,
     "_source": {
         "name": "cirros-0.3.4-x86_64-uec",
         "size": 25165824
     },
     "_type": "image",
     "sort": [
         "cirros-0.3.4-x86_64-uec",
         25165824
     ]
  },
  ...

Freeform queries
****************
Elasticsearch has a flexible query parser that can be used for many kinds of
search terms: the `query_string <http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/query-dsl-queries.html>`_
operator.

Some things to bear in mind about using ``query_string`` (see the documentation
for full options):

* A query term may be prefixed with a ``field`` name (as seen below). If it
  is not, by default the entire document will be searched for the term.
* The default operator between terms is ``OR``
* By default, query terms are case insensitive

For instance, the following will look for images with a
restriction on name and a range query on size::

  {
    "query": {
      "query_string": {
        "query": "name: (Ubuntu OR Fedora) AND size: [3000000 TO 5000000]"
      }
    }
  }

Wildcards
*********
Elasticsearch supports regular expression searches but often wildcards within
``query_string`` elements are sufficient, using ``*`` to represent one or more
characters or ``?`` to represent a single character. Note that *starting* a
search term with a wildcard can lead to *extremely* slow queries::

  {
    "query": {
      "query_string": {
        "query": "name: ubun?u AND mysql_version: 5.*"
      }
    }
  }

Highlighting
************
A common requirement is to highlight search terms in results::


  {
    "type": "OS::Glance::Metadefs",
    "query": {
      "query_string": {
        "query": "database"
      }
    },
    "fields": ["namespace", "description"],
    "highlight": {
      "fields": {
        "namespace": {},
        "description": {}
      }
    }
  }

Results::

  {
    "hits": {
      "hits": [
        {
          "_id": "OS::Software::DBMS",
          "_index": "searchlight",
          "_type": "OS::Glance::Metadef",
          "_score": 0.56079304,
          "_source": {
            "description": "A database is an organized collection of data. The data is typically organized to model aspects of reality in a way that supports processes requiring information. Database management systems are computer software applications that interact with the user, other applications, and the database itself to capture and analyze data. (http://en.wikipedia.org/wiki/Database)"
          },
          "highlight": {
            "description": [
              "A <em>database</em> is an organized collection of data. The data is typically organized to model aspects of",
              " reality in a way that supports processes requiring information. <em>Database</em> management systems are",
              " computer software applications that interact with the user, other applications, and the <em>database</em> itself",
              " to capture and analyze data. (http://en.wikipedia.org/wiki/<em>Database</em>)"
            ],
            "display_name": [
              "<em>Database</em> Software"
            ]
          }
        }
      ],
      "max_score": 0.56079304,
      "total": 1
    },
    "timed_out": false,
    "took": 3
  }

