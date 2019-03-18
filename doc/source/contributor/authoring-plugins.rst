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

This documentation will use as an example the Neutron network plugin as a
reasonably complete and complex example.

Getting some data
-----------------
The very first thing you should do is figure out exactly what you're trying to
index. When I've developed plugins I've found it helpful to generate test data
both for initial indexing and for notifications.

Initial indexing
^^^^^^^^^^^^^^^^
In the case of neutron networks, the initial data will come from
``neutronclient``. Some browsing of the API documentation reveals that the
call I want is ``list_networks``::

    import os

    from oslo_serialization import jsonutils

    from keystoneclient.auth.identity import v3
    from keystoneclient import session
    from neutronclient.v2_0 import client as nc_20

    def get_session():
        username = os.environ['OS_USERNAME']
        password = os.environ['OS_PASSWORD']
        auth_url = os.environ['OS_AUTH_URL']
        tenant_name = os.environ['OS_TENANT_NAME']
        auth = v3.Password(**locals())
        return session.Session(auth=auth)


    nc = nc_20.Client(session=get_session())
    networks = nc.list_networks()

    print(jsonutils.dumps(networks, indent=4, sort_keys=True))

This outputs::

    {
        "networks": [
            {
                "admin_state_up": true,
                "availability_zone_hints": [],
                "availability_zones": [
                    "nova"
                ],
                "created_at": "2016-04-08T16:44:17",
                "description": "",
                "id": "4d73d257-35d5-4f4e-bc71-f7f629f21904",
                "ipv4_address_scope": null,
                "ipv6_address_scope": null,
                "is_default": true,
                "mtu": 1450,
                "name": "public",
                "port_security_enabled": true,
                "provider:network_type": "vxlan",
                "provider:physical_network": null,
                "provider:segmentation_id": 1053,
                "router:external": true,
                "shared": false,
                "status": "ACTIVE",
                "subnets": [
                    "abcc5896-4844-4870-a5d8-6ae4b8edd42e",
                    "ea47304e-bd54-4337-901a-1eb5196ea18e"
                ],
                "tags": [],
                "tenant_id": "fa1537e9bda9405891d004ef9c08d0d1",
                "updated_at": "2016-04-08T16:44:17"
            }
        ]
    }

Since that's the output from neutron client, that's what should go in
``searchlight/tests/functional/data/load/networks.json``, though you might
also want more examples to test different things.

Notifications
^^^^^^^^^^^^^
Openstack documents some of the notifications_ sent by some services. It's
also possible to eavesdrop on notifications sent by running services. Taking
neutron as an example (though all services are slightly different), we can
make it output notifications by editing ``/etc/neutron/neutron.conf`` and
adding under the ``[oslo_messaging_notifications]`` section::

    driver = messagingv2

There are then two ways to configure the service to send notifications that
Searchlight can receive. The recommended method is to use notification pools,
touched on in the `messaging documentation`_.

.. _`messaging documentation`:

https://docs.openstack.org/oslo.messaging/latest/reference/notification_listener.html

Notification pools
##################

A notification messaging pool allows additional listeners to receive
messages on an existing topic. By default, Openstack services send notification
messages to an oslo.messaging 'topic' named `notifications`. To view these
notifications while still allowing ``searchlight-listener`` or Ceilometer's
agent to continue to receive them, you may use the utility script in
``test-scripts/listener.py``::

    . ~/devstack/openrc admin admin
    # If your rabbitmq user/pass are not the same as for devstack, you
    # can set RABBIT_PASSWORD and/or RABBIT_USER
    ./test-scripts/listener.py neutron test-notifications

Adding a separate topic
#######################

In the same config file (``/etc/neutron/neutron.conf``) the following line
(again, under the ``[DEFAULT]`` section) will cause neutron to output
notifications to a topic named ``searchlight_indexer``::

    notification_topics = searchlight_indexer

.. note::

    ``searchlight-listener`` also listens on the ``searchlight_indexer``
    topic, so if you have ``searchlight-listener`` running, it will receive
    and process some or all of the notifications you're trying to look at.
    Thus, you should either stop the ``searchlight-listener`` or add another
    topic (comma-separated) for the specific notifications you want to see.
    For example::

        notification_topics = searchlight_indexer,my_test_topic

After restarting the ``q-svc`` service notifications will be output to the
message bus (rabbitmq by default). They can be viewed in any RMQ management
tool; there is also a utility script in ``test-scripts/listener.py`` that
will listen for notifications::

    . ~/devstack/openrc admin admin
    # If your rabbitmq user/pass are not the same as for devstack, you
    # can set RABBIT_PASSWORD and/or RABBIT_USER
    ./test-scripts/listener.py neutron

.. note::

    If you added a custom topic as described above, you'll need to edit
    ``listener.py`` to use your custom topic::

        # Change this line
        topic = 'searchlight_indexer'
        # to
        topic = 'my_test_topic'

Using the results
#################

Issuing various commands (``neutron net-create``, ``neutron net-update``,
``neutron net-delete``) will cause ``listener.py`` to receive notifications.
Usually the notifications with ``event_type`` ending ``.end`` are the ones of
most interest (many fields omitted for brevity)::

    {"event_type": "network.update.end",
     "payload": {
       "network": {
         "status": "ACTIVE",
         "router:external": false,
         "subnets": ["9b6094de-18cb-46e1-8d51-e303ff844c86",
                     "face0b47-40d3-45c0-9b62-5f05311710f5",
                     "7b7bdf5f-8f22-44a3-bec3-1daa78df83c5"],
         "updated_at": "2016-05-03T19:05:38",
         "tenant_id": "34518c16d95e40a19b1a95c1916d8335",
         "id": "abf3a939-4daf-4d05-8395-3ec735aa89fc", "name": "private"}
      },
      "publisher_id": "network.devstack",
      "ctxt": {
        "read_only": false,
        "domain": null,
        "project_name": "demo",
        "user_id": "c714917a458e428fa5dc9b1b8aa0d4d6"
      },
      "metadata": {
        "timestamp": "2016-05-03 19:05:38.258273",
        "message_id": "ec9ac6a1-aa17-4ee3-aa6e-ab48c1fb81a8"
      }
    }

The entire message can go into
``searchlight/tests/functional/data/events/network.json``. The ``payload``
(in addition to the API response) will inform the mapping that should be
applied for a given plugin.

.. _notifications: https://wiki.openstack.org/wiki/SystemUsageData

File structure
--------------
Plugins live in ``searchlight/elasticsearch/plugins``. We have tended to create
a subpackage named after the service (``neutron``) and within it a module named
after the resource type (``networks.py``). Notification handlers can be in a file
specific to each resource type but can also be in a single file together
(existing ones use ``notification_handlers.py``).

``networks.py`` contains a class named ``NetworkIndex`` that implements the base
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
        os_neutron_net = searchlight.elasticsearch.plugins.neutron.networks:NetworkIndex

.. note::

    After modifying entrypoints, you'll need to reinstall the searchlight
    package to register them (you may need to activate your virtual environment;
    see :ref:`Installation Instructions`)::

        python setup.py develop

.. _Stevedore: https://docs.openstack.org/stevedore/latest/
.. _Heat: https://docs.openstack.org/heat/latest/template_guide/openstack.html

Writing some code
-----------------
At this point you're probably about ready to start filling in the code. My
usual approach is to create the unit test file first, and copy some of the
more boilerplate functionality from one of the other plugins.

You can run an individual test file with::

    tox -epy34 searchlight.tests.unit.<your test module>

This has the advantage of running just your tests and executing them very
quickly. It can be easier to start from a full set of failing unit tests
and build up the actual code from there. Functional tests I've tended to add
later. Again, you can run an individual functional test file:

    tox -epy34 searchlight.tests.functional.<your test module>

Required plugin functions
-------------------------
This section describes some of the functionality from ``IndexBase`` you will
need to override.

Document type
^^^^^^^^^^^^^
As a convention, plugins define their document type (which will map to an
ElasticSearch document type) as the `resource name`_ Heat uses to identify it::

    @classmethod
    def get_document_type(self):
        return "OS::Neutron::Net"

.. _`resource name`: https://docs.openstack.org/heat/latest/template_guide/openstack.html

Retrieving object for initial indexing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Plugins must implement ``get_objects`` which in many cases will go to the
API of the service it's indexing. It should return an iterable that will be
passed to a function (also required) named ``serialize``, which in turn must
return a dictionary suitable for Elasticsearch to index. In the example for
Neutron networks, this would be a call to ``list_networks`` on an instance of
``neutronclient``::

    def get_objects(self):
        """Generator that lists all networks owned by all tenants."""
        # Neutronclient handles pagination itself; list_networks is a generator
        neutron_client = openstack_clients.get_neutronclient()
        for network in neutron_client.list_networks()['networks']:
            yield network

Mapping
^^^^^^^

``get_mapping`` is also required. It must return a dictionary that tells
Elasticsearch how to map documents for the plugin (see the documentation for
mapping_).

At a minimum a plugin should define an ``id`` field and an ``updated_at`` field
because consumers will generally rely on those being present; a ``name`` field
is highly advisable. If the resource doesn"t contain these values your
``serialize`` function can map to them. In particular, if your resource does
not have a native ``id`` value, you must override ``get_document_id_field``
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


If you are mapping a field which is a reference id to other plugin type, you
should add a _meta mapping for that field. This will enable Searchlight(SL) to
provide more information to CLI/UI. The reference id and the plugin resource
type can be used by CLI/UI to issue a ``GET`` request to fetch more information
from SL. See below for an example on nova server plugin mapping::

  def get_mapping(self):
    return {
        'dynamic': True,
        'properties': {
            'id': {'type': 'string', 'index': 'not_analyzed'},
            'name': {
                'type': 'string',
                'fields': {
                    'raw': {'type': 'string', 'index': 'not_analyzed'}
                }
            }
            'image': {
                'type': 'nested',
                'properties': {
                    'id': {'type': 'string', 'index': 'not_analyzed'}
                }
            }
        },
        "_meta": {
            "image.id": {
                "resource_type": resource_types.GLANCE_IMAGE
            }
        },
    }

.. note:: Parent plugin id field(when available) is automatically linked to the
          parent resource type.

Doc values
^^^^^^^^^^

For many field types Searchlight will alter the mapping to change the format in
which field data is stored. Prior to Elasticsearch 2.x field values by default
were stored in 'fielddata' format, which could result in high memory usage under
some sort and aggregation operations. An alternative format, called ``doc_values``
trades slightly increased disk usage for better memory efficiency. In Elasticsearch
2.x ``doc_values`` is the default, and Searchlight uses this option as the default
regardless of Elasticsearch version. For more information see the Elasticsearch
documentation_.

.. _documentation: https://www.elastic.co/guide/en/elasticsearch/reference/2.1/doc-values.html

Generally this default will be fine. However, there are several ways in which
the default can be overridden:

* Globally in plugin configuration; in ``searchlight.conf``::

    [resource_plugin]
    mapping_use_doc_values = false

* For an individual plugin in ``searchlight.conf``::

    [resource_plugin:os_neutron_net]
    mapping_use_doc_values = false

* For a plugin's entire mapping; in code, override the ``mapping_use_doc_values``
  property (and thus ignoring any configuration property)::

    @property
    def mapping_use_doc_values(self):
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
type. A document will match the RBAC filters if any of the clauses match.
Administrative users can specify ``all_projects`` in searches to bypass
these filters. This default behavior can be overridden for a plugin by setting
the ``allow_admin_ignore_rbac`` property to ``False`` on the plugin (currently
only in code). ``all_projects`` will be ignore for that plugin.

Policy
^^^^^^
Related to access control is policy. Most services control API access with
policy files that define rules enforced with `oslo.policy`_. Searchlight has
its own policy file that configures access to its own API and resources, but
it also supports reading other services' policy files. In the future this will
be expanded to define RBAC rules, but at present external policy files are
only used to determine whether a resource should be available to a user.

To support this in your plugin, you must define two properties. The first
is ``service_type`` which must correspond to the service 'type' as seen
in the keystone catalog (e.g. nova's service 'type' is 'compute'). The
second property is ``resource_allowed_policy_target`` which identifies the
rule name in the service's policy files. If either of these properties are
'None' no rule will be enforced.

For example::

    @property
    def resource_allowed_policy_target(self):
        return 'os_compute_api:servers:index'

    @property
    def service_type(self):
        return 'compute'

See :ref:`service-policy-controls` for configuration information.

.. _oslo.policy: https://docs.openstack.org/oslo.policy/latest/

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
``provider:`` as well as any defined in the plugin configuration::

    @property
    def admin_only_fields(self):
        from_conf = super(NetworkIndex, self).admin_only_fields
        return ['provider:*'] + from_conf

These fields end up getting indexed in separate admin-only documents.

Parent/child relationships
--------------------------
In some cases there is a strong ownership implied between plugins. In these
cases the child plugin can define ``parent_plugin_type`` and
``get_parent_id_field`` (which determines a field on the child that refers
to its parent). See the Neutron ``Port`` plugin for an example.

Remember that Elasticsearch is not a relational database and it doesn't do
joins, per se, but this linkage does allow running queries referencing children
(or parents).

.. _mapping: https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html

Pipeline architecture
---------------------
Notification handlers can emit enriched resource data into pipeline, configured
publishers could use these data to notify external systems. To use this feature,
each event handler should return one or a sequence of pipeline items. These items
will be passed to subscribed publshers::

        def create_or_update(self, event_type, payload, timestamp):
            network_id = payload['network']['id']
            LOG.debug("Updating network information for %s", network_id)

            network = serialize_network(payload['network'])
            version = self.get_version(network, timestamp)

            self.index_helper.save_document(network, version=version)
            return pipeline.IndexItem(self.index_helper.plugin,
                                      event_type,
                                      payload,
