.. -*- rst -*-

Search
******

Provides indexing and search capabilities across OpenStack resources.

General information
~~~~~~~~~~~~~~~~~~~

The OpenStack Searchlight project provides a Search API that presents an
interface for querying about the various resources available in an OpenStack
cloud.  Searchlight creates an index (using open source Elasticsearch
technology) and keeps it updated.  Additionally, Searchlight's Search API
requires authentication and respects the Role Based Access Control defined by
each OpenStack service.  This gives end users access to the powerful searching
facilities provided by Elasticsearch, but operators can rest assured that end
users won't have access to information they wouldn't be able to find in the
APIs exposed by each of the OpenStack services.

The Search API allows you to construct detailed queries using the
`Elasticsearch Query Domain Specific Language
<http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/query-dsl.html>`_.
That's great if you are an Elasticsearch expert (or want to become one), but is
probably beyond what most end users need in order to use the Search API
effectively.  So we'll provide a wide range of useful query examples below (see
`Create a general search`_).

To make effective use of the Search API, you need to know a few things about
OpenStack resource types, how Searchlight stores data about OpenStack
resources, and something about Searchlight plugins.

OpenStack resource types
------------------------

An OpenStack cloud offers users many resources, for example, servers, images,
networks.  In order to eliminate ambiguity (for example, sometimes a resource
you create with Nova is called a "server", sometimes it's called an
"instance"), a standard vocabulary has developed based around that used by the
OpenStack `Heat <http://docs.openstack.org/developer/heat/>`_ project.

Heat identifies specific *resource types* that are assigned identifiers of the
form

``OS::{project_name}::{resource}``

where ``{project_name}`` and ``{resource}`` are replaced by an actual project
name and resource name.  For example, a Nova server (or "instance") has the
resource type identifier ``OS::Nova::Server``.

A list of OpenStack resource type identifiers is maintained by the Heat project
at `OpenStack Resource Types
<http://docs.openstack.org/developer/heat/template_guide/openstack.html>`_.

To summarize, you need to know the identifier for each OpenStack resource type
you're interested in so that you can efficiently search for those resources.

Searchlight data
----------------

Searchlight creates a *document* to represent each individual item (server,
image, network) in an OpenStack cloud.  These documents are stored in an
Elasticsearch *index*.  When you make a query using the Search API, the
documents appropriate to your query (and your RBAC roles) are returned to you.

To facilitate searching, each *document* has a *document type*.  Searchlight
uses the OpenStack *resource type* (described in the previous section) as the
*document type*.  For example, a virtual machine image stored in Glance would
be represented by a *document* with the *document type* ``OS::Glance::Image``.

The particular *document* that corresponds to an individual OpenStack resource
requires a unique identifier.  It just so happens that each OpenStack service
already assigns a unique identifier to each individual resource it controls, so
that's what Searchlight assigns as the *document ID*.  For example, if you have
an image in Glance with ID ``997ec7e8-a46b-4ab7-a1d4-788e06f52abe``, then that
image will be represented in the *index* by a *document* with a *document ID*
of ``997ec7e8-a46b-4ab7-a1d4-788e06f52abe``.

The information in the document will be the same content that would be
available to you if you queried the native API that handles that particular
resource type.  For example, a document with *document type*
``OS::Glance::Image`` will contain the same information about an image as you
would receive if you queried the Images API for information about that image.
The advantage to using Searchlight, of course, is that you have access to
advanced searching facilities provided by Elasticsearch.

Searchlight index
-----------------

In the previous section, you learned that each document stored in Elasticsearch
is uniquely identified by (a) what *index* it's in, (b) what *document type* it
has, and (c) what its *document ID* is.  You already know how to determine the
*document type* (it's the resource type of the OpenStack resource you're
interested in) and the *document ID* (it's the same as the identifier assigned
to the resource by the OpenStack service that manages that resource).  So
what's left is to figure out what index to use.

Due to careful engineering by top professionals, that's pretty easy.
Searchlight maintains its own index named 'searchlight'.  Further, the Search
API automatically uses this index, so you don't need to specify it.  We only
mention it here because you'll see its name in some Elasticsearch responses
that you'll receive from the Search API, so it's worth knowing what it is.

One final point. Searchlight accomplishes its magic by using *plugins* that
understand and index particular OpenStack resource types.  So in order for a
resource type to be accessible via the Search API, there must be a Searchlight
plugin installed to index that kind of resource.  Not all OpenStack resources
currently have Searchlight plugins associated with them, and not all OpenStack
deployers may have installed all available plugins.  You can determine what's
available in a particular cloud by using the `List plugins`_ call.

.. TODO(rosmaita): include authentication section? what are other api-ref
   doing?

   Authentication
   --------------

   Like other OpenStack APIs, the Search API depends on Keystone and the
   OpenStack Identity API to handle authentication.  Hence, you must obtain an
   authentication token from Keystone and pass it to Searchlight in API
   requests with the ``X-Auth-Token`` header.

List plugins
~~~~~~~~~~~~

.. rest_method::  GET /v1/search/plugins

List the supported plugins.

In order to index OpenStack resources, Searchlight requires a *plugin* specific
to each resource type.  Hence, the only resources that can be indexed in a
particular OpenStack cloud are those for which (a) a plugin exists, and (b) the
plugin is enabled by the cloud operator.  You use this call to determine what
document types you can expect to be able to search in a particular cloud.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

There are no request parameters, and this call does not take a request body.

Response
--------

.. rest_parameters:: search-parameters.yaml

   - plugins: plugin-list

Response Example
----------------

.. literalinclude:: samples/list-plugins-response.json
   :language: json

List facets
~~~~~~~~~~~

.. rest_method::  GET /v1/search/facets

List the supported facets.

For each registered resource type, Searchlight can provide a list of *field
names* and *values* present for those fields.

- Which fields are returned and whether values are listed is determined by
  each plugin.
- Some fields or values may only be listed for administrative users.
- For some string fields, ``facet_field`` may be included in the result.  If
  present, it can be used to do an exact term match against facet options.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

.. rest_parameters:: search-parameters.yaml

   - exclude_options: options-in-query
   - include_fields: include-in-query
   - type: type-in-query

.. NOTE(rosmaita): we can force extra space below the parameters
   table by inserting raw html here, but it would be better to
   put up a patch on the os-api-ref project to modify the style in CSS

.. TODO(rosmaita): remove this example

.. raw:: html

   <p></p>

This call does not take a request body.

Response
--------

.. rest_parameters:: search-parameters.yaml

   - facets: facet-list

Response Example
----------------

.. TODO(rosmaita): decide what to do about admin-only field in
   the example response

.. literalinclude:: samples/list-facets-all-response.json
   :language: json

Response Example (including ``exclude_options`` query parameter)
----------------------------------------------------------------

Assume this request: ``GET /v1/search/facets?exclude_options=true``

.. literalinclude:: samples/list-facets-all-response-exclude-options.json
   :language: json

Response Example (including ``type`` query parameter)
-----------------------------------------------------

Assume this request: ``GET /v1/search/facets?type=OS::Nova::Server``

.. literalinclude:: samples/list-facets-type-response.json
   :language: json

Response Example (including ``include_fields`` query parameter)
---------------------------------------------------------------

Assume this request: ``GET /v1/search/facets?include_fields=false``

.. literalinclude:: samples/list-facets-include-fields-response.json
   :language: json

.. _general-search:

Create a general search
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1/search

Submit a search request.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

.. rest_parameters:: search-parameters.yaml

   - Content-type: Content-type-json
   - query: es-query

Request Example
---------------

.. literalinclude:: samples/create-search-all-request.json
   :language: json

Response
--------

.. rest_parameters:: search-parameters.yaml

   - _shards: es-shards-obj
   - hits: es-hits-obj
   - timed_out: es-timed-out-field
   - took: es-took-field

Response Example
----------------

.. literalinclude:: samples/create-search-all-response.json
   :language: json

Create a type restricted search
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1/search

Request a type restricted search.

By including a ``type`` field in your request, you can restrict
the results to a particular resource type or types.

The ``type`` field can take either a string value (the name of
a particular resource type) or an array of values (where each
value is the name of a resource type).

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

.. rest_parameters:: search-parameters.yaml

   - Content-type: Content-type-json
   - query: es-query
   - type: type-in-body

Request Example (single resource type)
--------------------------------------

This example illustrates a request for a single resource type, Glance images.

.. literalinclude:: samples/create-search-single-type-request.json
   :language: json

Request Example (multiple resource types)
-----------------------------------------

This example illustrates a request for multiple resource types, Glance images
and Glance metadefs.

.. literalinclude:: samples/create-search-multiple-type-request.json
   :language: json

Response
--------

.. rest_parameters:: search-parameters.yaml

   - _shards: es-shards-obj
   - hits: es-hits-obj
   - timed_out: es-timed-out-field
   - took: es-took-field

Response Example (single resource type)
---------------------------------------

This example illustrates the response to a request for a single resource type,
Glance images (``OS::Glance::Image``).

.. literalinclude:: samples/create-search-single-type-response.json
   :language: json

Response Example (multiple resource types)
------------------------------------------

This example illustrates the resonse to a request for multiple resource types,
Glance images (``OS::Glance::Image``) and Glance metadefs
(``OS::Glance::Metadef``).

.. literalinclude:: samples/create-search-all-response.json
   :language: json

Create an administrative search
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1/search

Submit an administrative search request.

By default, the results a user receives in a search response are limited
to public resources and those resources owned by (or shared with) the user's
project (or "tenant").

Administrators have the option to view all resources in the index by passing
the ``all_projects`` field in the search request body.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

.. rest_parameters:: search-parameters.yaml

   - Content-type: Content-type-json
   - query: es-query
   - all_projects: all-projects

Request Example
---------------

.. literalinclude:: samples/create-search-admin-request.json
   :language: json

Response
--------

.. rest_parameters:: search-parameters.yaml

   - _shards: es-shards-obj
   - hits: es-hits-obj
   - timed_out: es-timed-out-field
   - took: es-took-field

Response Example
----------------

.. literalinclude:: samples/create-search-all-response.json
   :language: json

Create a free text search
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1/search

Submit a free text search request.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

.. rest_parameters:: search-parameters.yaml

   - Content-type: Content-type-json
   - type: type-in-body
   - multi_match: multi_match-in-body

Request Example
---------------

Suppose you want to find all images that have the word "cirros" in some field,
whether the in the name, tags, or any other image properties.

.. literalinclude:: samples/create-search-free-text-request.json
   :language: json

Response
--------

.. rest_parameters:: search-parameters.yaml

   - _shards: es-shards-obj
   - hits: es-hits-obj
   - timed_out: es-timed-out-field
   - took: es-took-field

Response Example
----------------

.. literalinclude:: samples/create-search-free-text-response.json
   :language: json

Create a phrase search
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1/search

Submit a search request that looks for a phrase in a particular field.

A common scenario is that you have custom metadata on some resources describing
the resource in natural language.  For example, you may have set a property
named ``description`` on your images, where the value is a natural language
sentence describing the recommended uses for that image.  You can query the
Search API for responses that match that phrase in that field.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

Suppose you use a ``description`` property on images as described above, and
you are interested in finding any images that are described as "Preconfigured
with a schmaltz to optimize the foobar."

.. rest_parameters:: search-parameters.yaml

   - Content-type: Content-type-json
   - query: es-query

Request Example
---------------

.. literalinclude:: samples/create-search-phrase-field-request.json
   :language: json

Response
--------

.. rest_parameters:: search-parameters.yaml

   - _shards: es-shards-obj
   - hits: es-hits-obj
   - timed_out: es-timed-out-field
   - took: es-took-field


Response Example
----------------

.. literalinclude:: samples/create-search-phrase-field-response.json


Create a compound boolean search
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1/search

Submit a compound boolean search request.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

.. rest_parameters:: search-parameters.yaml

   - Content-type: Content-type-json
   - query: es-query

Request Example
---------------

Suppose you want to find all the images that meet the following set of
conditions:

- The image must be *public* and *active*. (This is a *must clause*.)
- The image *cannot require more than 4096 RAM*. (This is a *must_not clause
  with a range query*.)
- The image must *not* be ``aki`` or ``ari``.  (This is a *must_not clause*)
- Either the *name* or the *tags* should contain "cirros". (This is a *should
  clause with minimum match of 1*.)
- In the results, indicate ("highlight") why these results were included in the
  request.

.. literalinclude:: samples/create-search-complex-boolean-request.json
   :language: json

Response
--------

.. rest_parameters:: search-parameters.yaml

   - _shards: es-shards-obj
   - hits: es-hits-obj
   - timed_out: es-timed-out-field
   - took: es-took-field

Response Example
----------------

.. literalinclude:: samples/create-search-complex-boolean-response.json


Create an aggregated search
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1/search

Submit an aggregated search request.

.. rest_status_code:: success http-codes.yaml

  - 200

.. rest_status_code:: error http-codes.yaml

  - 400
  - 401
  - 403
  - 500

Request
-------

.. rest_parameters:: search-parameters.yaml

   - Content-type: Content-type-json
   - query: es-query

Request Example
---------------

Suppose you want to find a count of the different names and container_formats
in all images.

.. literalinclude:: samples/create-search-aggregation-request.json
   :language: json

Response
--------

.. rest_parameters:: search-parameters.yaml

   - _shards: es-shards-obj
   - hits: es-hits-obj
   - aggregations: es-aggregate-obj
   - timed_out: es-timed-out-field
   - took: es-took-field

Response Example
----------------

.. literalinclude:: samples/create-search-aggregation-response.json


Notes
~~~~~

The index you see in responses is not a literal ElasticSearch index.
Here are a few points to keep in mind:

- For architectural reasons (primarily to allow zero-downtime re-indexing),
  Searchlight doesn't refer to the index directly, but instead uses *index
  aliases*. The key impact this has on you as a consumer of the API is that
  you'll see references to aliases, instead of directly to the index, in
  some Search API responses.
- All accesses to ElasticSearch are done through aliases and not directly
  through an index. For more details on aliases see the `List plugins`_
  call. The actual indices behind the aliases are transient, since a new
  one is created whenever Searchlight is re-indexed.
- By default, Searchlight uses a single index named 'searchlight'. An
  operator, however, may choose to use a different name.  Further, an
  operator may choose to have different resource types indexed into
  different indices so that, for example, "OS::Cinder::Volume" can have one
  Elasticsearch index, "OS::Neutron::Net" can have a different Elasticsearch
  index and "OS::Neutron::SecurityGroup" can have a third separate
  ElasticSearch index. When this is done, the aliases exposed via the
  Searchlight API will also change accordingly.


References
~~~~~~~~~~

- `Bool Query
  <https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html>`_
- `Range Query
  <https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html>`_
- `Highlighting
  <https://www.elastic.co/guide/en/elasticsearch/reference/current/search-request-highlighting.html>`_
- `Compound Queries
  <https://www.elastic.co/guide/en/elasticsearch/reference/current/compound-queries.html>`_
- `Aggregate Queries
  <https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html>`_
