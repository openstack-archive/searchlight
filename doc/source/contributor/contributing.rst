============================
So You Want to Contribute...
============================

For general information on contributing to OpenStack, please check out the
`contributor guide <https://docs.openstack.org/contributors/>`_ to get started.
It covers all the basics that are common to all OpenStack projects: the accounts
you need, the basics of interacting with our Gerrit review system, how we
communicate as a community, etc.

Below will cover the more project specific information you need to get started
with Searchlight.

Communication
~~~~~~~~~~~~~~
.. This would be a good place to put the channel you chat in as a project; when/
   where your meeting is, the tags you prepend to your ML threads, etc.

- IRC channel: #openstack-searchlight
- Mailing list's prefix: [searchlight]
- Meeting Times: http://eavesdrop.openstack.org/#Searchlight_Team_Meeting
- Meeting Agenda: https://etherpad.openstack.org/p/search-team-meeting-agenda
- Meeting Logs: http://eavesdrop.openstack.org/meetings/openstack_search

Contacting the Core Team
~~~~~~~~~~~~~~~~~~~~~~~~~
.. This section should list the core team, their irc nicks, emails, timezones etc. If
   all this info is maintained elsewhere (i.e. a wiki), you can link to that instead of
   enumerating everyone here.

- Trinh Nguyen <dangtrinhnt@gmail.com> (PTL) - dangtrinhnt - GMT+9
- Thuy Dang <thuydang.de@gmail.com> - thuydang - GMT+1

New Feature Planning
~~~~~~~~~~~~~~~~~~~~
.. This section is for talking about the process to get a new feature in. Some
   projects use blueprints, some want specs, some want both! Some projects
   stick to a strict schedule when selecting what new features will be reviewed
   for a release.

1. Talk to the team via IRC (meeting) or ML (with [searchlight] prefix) about
   the feature you want to add. We will discuss and figure out what is the best
   way forward considering our plan for the development cycle.
2. After the team has discussed and everyone agreed to have your feature
   landed in the current cycle, you can propose a blueprint document describing your
   feature in details (e.g., architecture, components, usage, etc.)
3. The team will review your blueprint and make comments until it is good enough
   to start implementing the feature.
4. You implement the feature based on the design in the blueprint.
5. Searchlight team will again review your code and approve it.

Task Tracking
~~~~~~~~~~~~~~
.. This section is about where you track tasks- launchpad? storyboard? is there more
   than one launchpad project? what's the name of the project group in storyboard?

We track our tasks in `Storyboard <https://storyboard.openstack.org/#!/project/openstack/searchlight>`_
If you're looking for some smaller, easier work item to pick up and get started
on, search for the 'low-hanging-fruit' tag.

.. NOTE: If your tag is not 'low-hanging-fruit' please change the text above.

Reporting a Bug
~~~~~~~~~~~~~~~
.. Pretty self explanatory section, link directly to where people should report bugs for
   your project.

You found an issue and want to make sure we are aware of it? You can do so
`HERE <https://storyboard.openstack.org/#!/project/openstack/searchlight>`_.

Getting Your Patch Merged
~~~~~~~~~~~~~~~~~~~~~~~~~
.. This section should have info about what it takes to get something merged. Do
   you require one or two +2's before +W? Do some of your repos require unit test
   changes with all patches? etc.

Due to the small number of core reviewers of the Searchlight project, we only need
one +2 before +W (merge). All patches excepting for documentation or typos fixes
must have unit test.


Project Team Lead Duties
------------------------
.. this section is where you can put PTL specific duties not already listed in
   the common PTL guide (linked below)  or if you already have them written
   up elsewhere, you can link to that doc here.

All common PTL duties are enumerated here in the `PTL guide <https://docs.openstack.org/project-team-guide/ptl.html>`_.
