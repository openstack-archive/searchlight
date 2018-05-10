..
      Copyright 2010 OpenStack Foundation
      All Rights Reserved.
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

Keystone Authentication
=======================

Searchlight should be integrated with keystone. Setting this up is
relatively straightforward, as the keystone distribution includes the
necessary middleware. Once you have installed keystone and edited your
configuration files, users will need to have an authenticated keystone token
in all API requests. The keystone integration will allow both active denial
of requests from unauthenticated users and will also allow proper search
result filtering.

.. DANGER::
   If the API is not configured with keystone, all data indexed by
   searchlight is at risk of being accessed by unauthorized users.


Configuring the searchlight services to use keystone
----------------------------------------------------

Keystone is integrated with searchlight through the use of middleware.
The default configuration files for the Searchlight API use a single piece of
middleware called ``unauthenticated-context``, which generates a request
context containing blank authentication information. In order to configure
Searchlight to use Keystone, the ``authtoken`` and ``context`` middleware
must be deployed in place of the ``unauthenticated-context`` middleware.
The ``authtoken`` middleware performs the authentication token validation
and retrieves actual user authentication information. It can be found in
the keystone distribution. For more information, please refer to the Keystone
documentation on the ``auth_token`` middleware:
https://docs.openstack.org/keystonemiddleware/latest/middlewarearchitecture.html

api-paste.ini
`````````````

First, ensure that declarations for the middleware exist in the
``api-paste.ini`` file.  Here is an example for ``authtoken``::

  [pipeline:searchlight-keystone]
  pipeline = authtoken context rootapp

  [filter:authtoken]
  paste.filter_factory = keystonemiddleware.auth_token:filter_factory
  delay_auth_decision = true

searchlight.conf
````````````````

You must then update the main ``searchlight.conf`` configuration file
to enable the keystone application pipeline.

Set ``flavor`` to ``keystone`` in the ``paste_deploy`` group::

  [paste_deploy]
  flavor = keystone

Set ``keystone_authtoken`` options. The following sets the searchlight
service user as the user for performing policy API authentication checks.
The actual options and values in this section will need to be set according
to your environment::

  [keystone_authtoken]
  auth_url = http://127.0.0.1:5000
  auth_type = password
  project_domain_id = default
  project_name = service
  user_domain_id = default
  password = <SERVICE_PASSWORD>
  username = searchlight

.. note::
  For development and unit testing, it is recommended to also set
  ``revocation_cache_timeout = 10`` under the ``keystone_authtoken`` group.

Set ``service_credentials`` options. Searchlight plugins may make API calls
to other services to index their data. Prior to doing this, it will get a
valid token based on the integration account credentials::

 [service_credentials]
 # These are needed to make API calls to other services when indexing
 auth_type = password
 username = searchlight
 password = <SERVICE_PASSWORD>
 user_domain_id = default
 project_domain_id = default
 project_name = service
 auth_url = http://127.0.0.1:5000

 # If resource_plugin.include_region_name is set, this value will be
 # the default value for the 'region_name' field on all documents
 # os_region_name =

For keystone v2 development::

 [service_credentials]
 auth_type = v2password
 username = searchlight
 tenant_name = service
 password = <SERVICE_PASSWORD>
 auth_url = http://127.0.0.1:35357/v2.0

 # If resource_plugin.include_region_name is set, this value will be
 # the default value for the 'region_name' field on all documents
 # os_region_name =


Service integration account
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Some of the above configuration implicitly uses a ``searchlight`` service user.
If you intend to use this user, it must have been created and registered with
keystone. Typically, this is done with the following commands (v3 keystone)::

  $ openstack project create --or-show service --property domain=default
  $ openstack user create searchlight --password <SERVICE_PASSWORD> --project service
  $ openstack role add admin --project service --user searchlight

For more information on keystone service accounts, see:

https://docs.openstack.org/keystone/latest/admin/cli-keystone-manage-services.html#create-service-users

Policy restriction
==================

Searchlight uses the oslo policy library to allow control over the level of
access a user has based on their authenticated roles. Policy rules are defined
in a configuration file (by default, `etc/policy.json`). By default, all
operations are allowed.

https://docs.openstack.org/oslo.policy/latest/reference/index.html
rule formatting.

During the last few cycles concerns were raised about the scope of the
``admin`` role within OpenStack. Many services consider any token scoped with
the ``admin`` role to have access to resources within any project. With the
introduction of keystone v3 it is possible to create users with the admin role
on a particular project, but not with the intention of them seeing resources in
other projects.

Keystone added two configuration options called ``admin_project_name`` and
``admin_project_domain_name`` to attempt to address this. If a request is
authenticated against a the project whose name is ``admin_project_name``
in the ``admin_project_domain_name`` domain, a flag is set on the
authentication response headers indicating that the user is authenticated
against the administrative project. This can then be supported by the policy
rule (in Searchlight's ``policy.json``)::

    "is_admin_context": "role:admin and is_admin_project:True"

Since devstack configures keystone to support those options, this is the
default in Searchlight. To maintain backwards compatibility, if your keystone
is *not* configured to set these options, any token with the ``admin`` role
will be assumed to have administrative powers (this approach has been taken
by other OpenStack services).

For more history see https://bugs.launchpad.net/keystone/+bug/968696.

Access to operations
--------------------

It is possible to restrict access to functionality by setting rules for
``query``, ``facets`` or ``plugins_info``. For instance, to restrict facet
listing to administrators and disable plugin information for all users::

    "facets": "role:admin",
    "plugins_info": "!"

Where a request is disallowed on this basis, the user will receive a
403 Forbidden response.

Note that policy rules are applied on the fly; no server restart is required.
Policy rules denying access to operations take precedence over the per-resource
access described below.

Access to resources
-------------------

It is possible to disable access to individual plugins. For instance, the
following restricts access to Nova servers to admins, and disables access
entirely to Glance images::

    "resource:OS::Nova::Server": "role:admin",
    "resource:OS::Glance::Image": "!",


.. note::

    At current plugins still apply RBAC separately from policy rules. We
    aim to bring the two closer together in a later patch.

When resources are restricted in this way resources will be excluded
from the search (which may result in empty search results). No Forbidden
response will be returned.

.. _service-policy-controls:

Service policy controls
-----------------------

If configured, Searchlight can consult service policy files (e.g. that used
to configure the nova API). Each resource is configured with a policy target
it will check if possible. Policy file paths can either be absolute or relative
to `service_policy_path` (which itself can be relative to the current working
directory or left blank). The actual filepath used will be determined by
oslo.config using the same `logic`_ as for other config files (for logging,
searchlight's policy file etc). With the following configuration
stanza::

    [service_policies]
    service_policy_files=compute:nova-policy.json
    service_policy_path=/etc/searchlight/

And with the following contents in nova-policy.json (which might be a symlink
to an existing nova policy file, a copy or a separate file)::

    {
        "is_admin": "role: admin",
        "os_compute_api:servers:index": "rule:is_admin"
    }

Only requests with the admin role assigned will be allowed to search or facet
Nova servers.

Policy files are configured per *service*, not per resource type. If files
are in different directories absolute paths should be used, and
``service_policy_path`` left unset.

.. note:: 

   Policy rules are always *more* restrictive. If a rule in Searchlight's
   ``policy.json`` would allow access but a service policy file would disallow
   it (or vice versa), the more restrictive rule will be used.

.. _logic: https://docs.openstack.org/oslo.config/latest/reference/configopts.html
