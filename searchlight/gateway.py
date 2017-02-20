# Copyright 2012 OpenStack Foundation
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

from searchlight.api import policy
import searchlight.elasticsearch


class Gateway(object):
    def __init__(self, policy_enforcer=None, es_api=None):
        self.policy = policy_enforcer or policy.Enforcer()
        if es_api:
            self.es_api = es_api
        else:
            self.es_api = searchlight.elasticsearch.get_api()

    def get_catalog_search_repo(self, context):
        search_repo = searchlight.elasticsearch.CatalogSearchRepo(
            context, self.es_api)
        policy_search_repo = policy.CatalogSearchRepoProxy(
            search_repo, context, self.policy)
        return policy_search_repo
