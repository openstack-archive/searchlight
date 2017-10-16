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

RESOURCE = 'resource:OS::%s'

rules = [
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Glance::Image',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Glance Image resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Glance::Metadef',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Glance Metadef resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Nova::Server',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Nova Server resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Nova::Hypervisor',
        check_str="rule:context_is_admin",
        description='Query with Nova Hypervisor resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Nova::ServerGroup',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Nova ServerGroup resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Nova::Flavor',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Nova Flavor resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Cinder::Volume',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Cinder Volume resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Cinder::Snapshot',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Cinder Snapshot resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Designate::Zone',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Designate Zone resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Designate::RecordSet',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Designate RecordSet resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Neutron::Net',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Neutron Net resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Neutron::Port',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Neutron Port resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Neutron::Subnet',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Neutron Subnet resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Neutron::Router',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Neutron Router resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Neutron::SecurityGroup',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Neutron SecurityGroup resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Ironic::Chassis',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Ironic Chassis resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Ironic::Node',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Ironic Node resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
    policy.DocumentedRuleDefault(
        name=RESOURCE % 'Ironic::Port',
        check_str=base.RULE_ADMIN_OR_OWNER,
        description='Query with Ironic Port resource.',
        operations=[
            {
                'path': '/v1/search',
                'method': 'POST'
            },
            {
                'path': '/v1/search',
                'method': 'GET'
            },
            {
                'path': '/v1/search/plugins',
                'method': 'GET'
            },
            {
                'path': '/v1/search/facets',
                'method': 'GET'
            }
        ]
    ),
]


def list_rules():
    return rules
