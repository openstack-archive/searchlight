..
    c) Copyright 2015 Hewlett-Packard Development Company, L.P.

    Licensed under the Apache License, Version 2.0 (the "License"); you may
    not use this file except in compliance with the License. You may obtain
    a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
    License for the specific language governing permissions and limitations
    under the License.

================================
Feature Requests and Bug Reports
================================

Searchlight is an open project and we encourage contribution from everybody.

We support both developers and non-developers who want to provide input,
requests for features, and bug fixes. We want to be able to move quickly
without getting too bogged down in process, but still provide a rich mechanism
for feature reviews as needed.


Workflow
========

Our process is meant to allow users, developers, and operators to express
their desires for new features using Storyboard blueprints. A review of
blueprints is done regularly. These may turn directly into features, or
for complex requests, additional specifications ("specs") may be needed.

The workflow is very simple:

* If something is clearly broken, submit a `bug report`_ in Storyboard.
* If you want to change or add a feature, submit a `blueprint`_ in Storyboard.
* Searchlight drivers may request that you submit a `specification`_ to gerrit to elaborate on the feature request
* Significant features require `Release Notes`_ to be included when the code is merged

.. note::

    If you already have code to submit, go ahead and submit a gerrit review!
    We encourage early code sharing. Just be aware that it needs to be cross
    linked with a bug or blueprint and may not be accepted without approval
    of the blueprint or bug. We also use the blueprint and bug priorities
    to guide our code review priorities.

We will review incoming bugs and blueprints on an ongoing basis. It is
always okay to ask for feedback on a bug or blueprint that has been submitted.
We always welcome you in the IRC channel, the mailing list, and the weekly
meeting. We just ask that you understand that there may be many reviews
happening at any point in time and it may take a little time for reviews to be
completed.

.. _bug report:

Bug Reports
-----------

Current Bugs are found here:

* https://storyboard.openstack.org/#!/project_group/93

A bug may be filed by adding a story.

Please provide information on what the problem is, how to replicate it,
any suggestions for fixing it, and a recommendation of the priority.

Security Bugs
~~~~~~~~~~~~~

Reporting bugs referencing security related vulnerabilities in released
versions of Searchlight requires additional consideration. A bug with security
implications should be filed as a private security bug. This prevents public
disclosure of potential security issues before they can be addressed.

To mark a bug as a private security bug, set the value for the field "This bug
contains information that is:" from "Public" to "Private Security". If you have
questions, please contact either of the following groups:

* `Searchlight Core Security Team <https://launchpad.net/~searchlight-coresec>`_
* `OpenStack Vulnerability Management Process <https://security.openstack.org/vmt-process.html>`_

In the event that a bug filed as a private security bug is determined not to
have security implications, the bug will be moved to a public bug report.

.. _blueprint:

Blueprints
----------

Current blueprints are found here:

* https://storyboard.openstack.org/#!/project_group/93

A blueprint may be filed by adding a story.

The initial blueprint primarily needs to express the intent of the idea with
enough details that the idea can be evaluated for compatibility with the
Searchlight mission and whether or not the change requires a
`specification`_ for change tracked reviews. It is *not*
expected to contain all of the implementation details. If the feature
is very simple and well understood by the team, then describe it simply.
Searchlight team members will request more information as needed.

If the blueprint starts to seem non-trivial, or seem like it will benefit
from a better tool for comments and change tracking, then you should
submit a `specification`_ to gerrit proactively and simply
link to it from your blueprint to accommodate better reviews.


.. _specification:

Specifications
--------------

We use the `searchlight-specs
<http://git.openstack.org/cgit/openstack/searchlight-specs>`_ repository for
specification reviews. Specifications:

* Provide a review tool for collaborating on feedback and reviews for complex features
* Serve as the basis for documenting the feature once implemented
* Ensure that the overall impact on the system is considered

The Searchlight team does not enforce deadlines for specs. These can be submitted
throughout the release cycle. The drivers team will review this on a regular
basis throughout the release, and based on the load for the milestones, will
assign these into milestones or move them to the backlog for selection into
a future release.

Please note that we use a `template
<http://git.openstack.org/cgit/openstack/searchlight-specs/tree/specs/template.rst>`_
for spec submissions. It is not required to fill out all sections in the
template. Review of the spec may require filling in information left out by
the submitter.

The review system will run a few tests to check the basic format and
syntax of your spec.  You will just need to run ``tox`` locally from within
the checked out spec repository to replicate the review tests.

Release Notes
=============

The release notes for a patch should be included in the patch. If not, the
release notes should be in a follow-on review.

If any of the following applies to the patch, a release note is required:

* The deployer needs to take an action when upgrading
* A new feature is implemented
* Plugin API function was removed or changed
* Current behavior is changed
* A new config option is added that the deployer should consider changing from
  the default
* A security bug is fixed
* Change may break previous versions of the client library(ies)
* Requirement changes are introduced for important libraries like oslo, six
  requests, etc.
* Deprecation period starts or code is purged

A release note is suggested if a long-standing or important bug is fixed.
Otherwise, a release note is not required.

Searchlight uses `reno <https://docs.openstack.org/reno/latest/user/usage.html>`_ to
generate release notes. Please read the docs for details. In summary, use
the following:

.. code-block:: bash

  $ tox -e venv -- reno new <bug-,bp-,whatever>

Then edit the sample file that was created and push it with your change.

To see the results:

.. code-block:: bash

  $ git commit  # Commit the change because reno scans git log.

  $ tox -e releasenotes

Then look at the generated release notes files in releasenotes/build/html in
your favorite browser.
