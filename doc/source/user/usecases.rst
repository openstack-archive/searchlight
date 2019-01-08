..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.


Searchlight Use Cases and Our Vision
====================================

Searchlight was originally developed and released in the Kilo release of
Glance as the Catalog Index Service [#]_. At the Liberty Summit, we decided
to broaden the scope to provide advanced and scalable search across
multi-tenant cloud resources. Over the years, we gathered feedbacks and
comments both from the cloud developers and users to clarify the real use
cases of Searchlight. We also developed a grand vision for Searchlight to help
sustain the project in a rapid changing world.


Use Cases
---------

Searchlight can be used in several scenarios such as:

* **Cloud resources lookup:** whenever the user needs to query some
  information of the desired OpenStack services (e.g. Nova, Neutron, etc.),
  instead of using the service's APIs individually, she only needs to use
  one single Searchlight web interface to perform all the queries. Currently,
  Searchlight supports indexing OpenStack services such as Cinder, Designate,
  Glance, Ironic, Neutron, Nova, and Swift. Searchlight also provides a
  context menu for quick operations on resource search results, e.g., creating
  an instance from an image.
* **Cloud resource repository:** because Searchlight keeps records of
  real-time notification data from other OpenStack's components, it is
  aware of the committed, available cloud resources, and other operational
  events. This capacity of Searchlight can be leveraged by virtual infrastructure
  management (VIM) applications, e.g., self-healing, self-configuration, RCA, etc.
  This is a work-in-progress [#]_.
* **Multi-cloud discovery:** Searchlight resource repositories can be connected
  forming a distributed resource discovery infrastructure across multi-cloud
  deployment, i.e., cross OpenStack domain, OpenStack-Azure, AWS, or Containers
  on OpenStack VMs. This new role of Searchlight can take advantages of the
  existing user-friendly interface for multi-cloud resource administrators [#]_
  while also providing a unified API for the automation of the resource
  management operation.


Our Vision
----------

With the modular architecture of Searchlight and based on the discussions of
the Searchlight team, we envisioned making Searchlight a universal search
interface not only for OpenStack but also other cloud platforms such as
Microsoft Azure [#]_, AWS [#]_, or even Kubernetes [#]_, etc.. The final
product of this vision could be building a multi-cloud management application
and a unified API for multi-cloud resource discovery, which serves as a
cloud information base for automation application, e.g., VIM management,
NFV MANO. This requires new designs of additional data models, APIs,
communication, and features which are analyzed further in specific use
case analysis & design documents. References will be provided when available.

.. figure:: ../../../images/SeaaS.png
   :width: 100%
   :alt: Search as a Service


References
----------

.. [#] http://specs.openstack.org/openstack/glance-specs/specs/kilo/catalog-index-service.html
.. [#] https://storyboard.openstack.org/#!/story/2004721
.. [#] https://www.slideshare.net/vietstack/building-a-universal-search-interface-for-the-cloud
.. [#] https://storyboard.openstack.org/#!/story/2004718
.. [#] https://storyboard.openstack.org/#!/story/2004719
.. [#] https://storyboard.openstack.org/#!/story/2004382
