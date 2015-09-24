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
from searchlight import i18n


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

DEFAULT_RULES = policy.Rules.from_dict({
    'context_is_admin': 'role:admin',
    'default': '@',
})

_ = i18n._
_LI = i18n._LI
_LW = i18n._LW


class Enforcer(policy.Enforcer):
    """Responsible for loading and enforcing rules"""

    def __init__(self):
        if CONF.find_file(CONF.oslo_policy.policy_file):
            kwargs = {'rules': None, 'use_conf': True}
        else:
            kwargs = {'rules': DEFAULT_RULES, 'use_conf': False}
        super(Enforcer, self).__init__(CONF, overwrite=False, **kwargs)

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
        credentials = {
            'roles': context.roles,
            'user': context.user,
            'tenant': context.tenant,
        }
        return super(Enforcer, self).enforce(action, target, credentials,
                                             do_raise=True,
                                             exc=exception.Forbidden,
                                             action=action)

    def check(self, context, action, target):
        """Verifies that the action is valid on the target in this context.

           :param context: Glance request context
           :param action: String representing the action to be checked
           :param target: Dictionary representing the object of the action.
           :returns: A non-False value if access is allowed.
        """
        credentials = {
            'roles': context.roles,
            'user': context.user,
            'tenant': context.tenant,
        }
        return super(Enforcer, self).enforce(action, target, credentials)

    def check_is_admin(self, context):
        """Check if the given context is associated with an admin role,
           as defined via the 'context_is_admin' RBAC rule.

           :param context: Glance request context
           :returns: A non-False value if context role is admin.
        """
        return self.check(context, 'context_is_admin', context.to_dict())


class CatalogSearchRepoProxy(object):

    def __init__(self, search_repo, context, search_policy):
        self.context = context
        self.policy = search_policy
        self.search_repo = search_repo

    def search(self, *args, **kwargs):
        self.policy.enforce(self.context, 'catalog_search', {})
        return self.search_repo.search(*args, **kwargs)

    def plugins_info(self, *args, **kwargs):
        self.policy.enforce(self.context, 'catalog_plugins', {})
        return self.search_repo.plugins_info(*args, **kwargs)

    def index(self, *args, **kwargs):
        self.policy.enforce(self.context, 'catalog_index', {})
        return self.search_repo.index(*args, **kwargs)

    def facets(self, *args, **kwargs):
        self.policy.enforce(self.context, 'catalog_facets', {})
        return self.search_repo.facets(*args, **kwargs)
