===========================================================
Searchlight reflects on the 2018 OpenStack Technical Vision
===========================================================

In late-2018, the OpenStack Technical Committee composed a technical vision
[#]_ of what OpenStack clouds should look like. This document compares the
state of Searchlight relative to that vision to provide some guidance on
broad-stroke ways in which Searchlight may need to change to match the vision.
Note that there is also a Searchlight Vision document [#]_.

The TC vision document is divided into three sections, which this document
mirrors. This should be a living document which evolves as Searchlight itself
evolves.


The Pillars of Cloud
====================

While the Searchlight API performs read-only accesses of Elasticsearch for
user-facing features (i.e., search), the Searchlight Amin CLI provides
read-write access to Elasticsearch for administrative tasks (e.g., re-index
data, etc.), so basically, anything can talk to it, enabling the self-service
and application control features that define a cloud.


OpenStack-specific Considerations
=================================

Interoperability
----------------

Because Searchlight only has Keystone as a hard-dependency, Searchlight
deployment can be ported from one OpenStack cloud to another easily with
minimal modification of the settings depends on the services Searchlight want
to index.

Bidirectional Compatibility
---------------------------

Searchlight APIs is versioned and designed to allow client introspection of
the available versions and features.

Cross-Project Dependencies
--------------------------

Searchlight depends on Keystone to have universal access to other OpenStack
services and user authentication. Other services that Searchlight supports
(e.g., Nova, Cinder, Glance, etc.) are soft dependencies.

Partitioning
------------

At the current state, Searchlight only supports indexing resource information
of one single OpenStack instance where Searchlight deployed. In the Stein
cycle, we have designed a vision that is to make Searchlight a multi-cloud
solution. It means that Searchlight will be able to search resource
information across different cloud platforms and tenants. Moreover, by going
in that direction, Searchlight would offer features such as tagging and or
partitioning resource information arbitrarily.


Design Goals
============

Searchlight already maps well to most of the design goals in the TC vision
document such as scalability, reliability, customization, and flexible
utilization models. Searchlight also offers a graphical user interface to
query the indexed resources. We should strive to keep this. Details of how we
plan to do so should be maintained in the Searchlight Vision document.


References
==========

.. [#] https://governance.openstack.org/tc/reference/technical-vision.html

.. [#] https://docs.openstack.org/searchlight/latest/contributor/searchlight-vision.html
