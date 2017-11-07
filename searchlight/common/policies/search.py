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
from oslo_policy import policy

from searchlight.common.policies import base

SEARCH = 'search:%s'

rules = [
    policy.DocumentedRuleDefault(
        name=SEARCH % 'query',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query a search.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=SEARCH % 'query:aggregations',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query a search with aggregation request.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=SEARCH % 'plugins_info',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Retrieve a list of installed plugins.',
        operations=[
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=SEARCH % 'facets',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='List supported facets.',
        operations=[
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    )
]


def list_rules():
    return rules
