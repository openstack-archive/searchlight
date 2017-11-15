# Copyright (c) 2011 OpenStack Foundation
# Copyright 2013 IBM Corp.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Policy Engine For Searchlight"""

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import policy

from searchlight.common import exception
from searchlight.common import policies
from searchlight import service_policies


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

DEFAULT_RULES = policy.Rules.from_dict({
    'context_is_admin': 'role:admin',
    'default': '@',
})


class Enforcer(policy.Enforcer):
    """Responsible for loading and enforcing rules"""

    def __init__(self):
        if CONF.find_file(CONF.oslo_policy.policy_file):
            kwargs = {'rules': None, 'use_conf': True}
        else:
            kwargs = {'rules': DEFAULT_RULES, 'use_conf': False}
        super(Enforcer, self).__init__(CONF, overwrite=False, **kwargs)
        self.register_defaults(policies.list_rules())

    def add_rules(self, rules):
        """Add new rules to the Rules object"""
        self.set_rules(rules, overwrite=False, use_conf=self.use_conf)

    def enforce(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Searchlight request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :raises: `searchlight.common.exception.Forbidden`
           :returns: A non-False value if access is allowed.
        """
        credentials = context.to_dict()
        return super(Enforcer, self).enforce(action, target, credentials,
                                             do_raise=True,
                                             exc=exception.Forbidden,
                                             action=action)

    def check(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Searchlight request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        credentials = context.to_dict()
        return super(Enforcer, self).enforce(action, target, credentials)

    def check_is_admin(self, context):
        """Check if the given context is associated with an admin role,
           as defined via the 'context_is_admin' RBAC rule.

           :param context: Searchlight request context
           :returns: A non-False value if context role is admin.
        """
        return self.check(context, 'context_is_admin', context.to_dict())


class CatalogSearchRepoProxy(object):

    def __init__(self, search_repo, context, search_policy):
        self.context = context
        self.policy = search_policy
        self.search_repo = search_repo

    def search(self, *args, **kwargs):
        self.policy.enforce(self.context, 'search:query',
                            self.context.policy_target)
        return self.search_repo.search(*args, **kwargs)

    def plugins_info(self, *args, **kwargs):
        self.policy.enforce(self.context, 'search:plugins_info',
                            self.context.policy_target)
        return self.search_repo.plugins_info(*args, **kwargs)

    def facets(self, *args, **kwargs):
        self.policy.enforce(self.context, 'search:facets',
                            self.context.policy_target)
        return self.search_repo.facets(*args, **kwargs)


def plugin_allowed(policy_enforcer, context, plugin):
    """Returns True or False indicating whether a plugin should be available
    for API operations to a given user.
    """
    resource_type = plugin.get_document_type()
    policy_action = 'resource:%s' % resource_type
    service_type = plugin.service_type
    target = context.policy_target
    if not policy_enforcer.check(context, policy_action, target):
        LOG.debug("Policy for '%s' forbids '%s'",
                  policy_action, resource_type)
        return False

    # Now try any related policy action
    service_policy_action = plugin.resource_allowed_policy_target

    service_enforcer = service_policies.get_enforcer_for_service(service_type)

    if service_enforcer and service_policy_action:
        if not resource_allowed(service_enforcer, context,
                                service_policy_action):
            LOG.debug("Policy for '(%s) %s' forbids '%s'",
                      service_type, service_policy_action, resource_type)
            return False

    # (sjmc7) Current decision is not to enforce policy files for services,
    # though that might be an option that could be added. If a service
    # enforcer is configured improperly the server won't start.

    # At this point all tests that exist have passed, so allow the plugin
    return True


def resource_allowed(enforcer, context, resource_allowed_action, target={}):
    """Check whether 'resource_allowed_action' is allowed by 'enforcer' for
    the given context.
    """
    credentials = context.to_policy_values()
    if 'tenant_id' not in credentials:
        credentials['tenant_id'] = credentials.get('project_id', None)
    if 'is_admin' not in credentials:
        credentials['is_admin'] = context.is_admin

    if not target:
        # This allows 'admin_or_owner' type rules to work
        target = {
            'project_id': context.tenant,
            'user_id': context.user,
            'tenant_id': context.tenant
        }
    return enforcer.enforce(resource_allowed_action, target, credentials)
