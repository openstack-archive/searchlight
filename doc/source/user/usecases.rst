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


Searchlight Use Cases
=====================

Below are the use cases of Searchlight:

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


References
----------

.. [#] https://storyboard.openstack.org/#!/story/2004721
.. [#] https://www.slideshare.net/vietstack/building-a-universal-search-interface-for-the-cloud
