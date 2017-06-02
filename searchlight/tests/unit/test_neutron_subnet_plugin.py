# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime

from searchlight.common import utils
from searchlight.elasticsearch.plugins.neutron import\
    subnets as subnets_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


_now_str = utils.isotime(datetime.datetime.utcnow())
USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'
ID1 = "813dd936-663e-4e5b-877c-986021b73e2c"
NETID1 = "98dcb60c-59b9-4b3c-bf6a-b8504112e978"
TENANT1 = "8eaac046b2c44ab99246cb0850c7f06d"


def _subnet_fixture(network_id, tenant_id, subnet_id, name, **kwargs):
    fixture = {
        "id": subnet_id,
        "network_id": network_id,
        "name": name,
        "tenant_id": tenant_id,
        "ip_version": kwargs.pop("ip_version", 4),
        "cidr": kwargs.pop("cidr", "192.0.0.1/24")
    }
    pools = kwargs.get('allocation_pools', [{"start": "192.0.0.2",
                                             "end": "192.254.254.254"}])
    fixture['allocation_pools'] = pools
    fixture.update(kwargs)
    return fixture


class TestSubnetLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSubnetLoaderPlugin, self).setUp()
        self.plugin = subnets_plugin.SubnetIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.subnet1 = _subnet_fixture(subnet_id=ID1, network_id=NETID1,
                                       tenant_id=TENANT1, name="test-net-1")
        self.subnets = [self.subnet1]

    def test_document_type(self):
        self.assertEqual('OS::Neutron::Subnet',
                         self.plugin.get_document_type())

    def test_rbac_filter_admin_role(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=True
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)
        expected_rbac = [
            {'term': {'tenant_id': TENANT1}},
            {
                'has_parent': {
                    'type': self.plugin.parent_plugin_type(),
                    'query': {
                        "bool": {
                            "should": [
                                {'term': {'shared': True}},
                                {'term': {'router:external': True}}
                            ]
                        }
                    }
                }
            }
        ]

        self.assertEqual(expected_rbac, rbac_terms)

    def test_rbac_filter_non_admin_role(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)
        self.assertEqual(
            [{"term": {"tenant_id": TENANT1}},
             {
                "has_parent": {
                    "type": "OS::Neutron::Net",
                    "query": {"term": {"shared": True}}
                }
            }],
            rbac_terms
        )

    def test_notification_events(self):
        handler = self.plugin.get_notification_handler()
        self.assertEqual(
            set(['subnet.create.end', 'subnet.update.end',
                 'subnet.delete.end']),
            set(handler.get_event_handlers().keys())
        )
