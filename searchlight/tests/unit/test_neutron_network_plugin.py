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
import random

from searchlight.common import utils
from searchlight.elasticsearch.plugins.neutron import\
    networks as networks_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


_now_str = utils.isotime(datetime.datetime.utcnow())
USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'
ID1 = "813dd936-663e-4e5b-877c-986021b73e2c"
TENANT1 = "8eaac046b2c44ab99246cb0850c7f06d"


def _network_fixture(network_id, tenant_id, name, **kwargs):
    fixture = {
        "admin_state_up": True,
        "id": network_id,
        "mtu": 0,
        "name": name,
        "port_security_enabled": True,
        "provider:network_type": "vxlan",
        "provider:physical_network": None,
        "provider:segmentation_id": random.randint(1000, 1500),
        "router:external": False,
        "shared": False,
        "status": "ACTIVE",
        "subnets": [],
        "tenant_id": tenant_id,
        "updated_at": _now_str,
        "created_at": _now_str
    }
    fixture.update(kwargs)
    return fixture


class TestNetworkLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestNetworkLoaderPlugin, self).setUp()
        self.plugin = networks_plugin.NetworkIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.network1 = _network_fixture(
            network_id=ID1, tenant_id=TENANT1, name="test-net-1")
        self.networks = [self.network1]

    def test_default_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Neutron::Net',
                         self.plugin.get_document_type())

    def test_serialize(self):
        # Serialization doesn't do much right now; removes subnets
        serialized = self.plugin.serialize(self.network1)
        self.assertNotIn('subnets', serialized)
        self.assertEqual(_now_str, serialized['updated_at'])
        # project id should get copied from tenant_id
        self.assertEqual(TENANT1, serialized['project_id'])
        self.assertEqual([], serialized['members'])
        self.assertEqual([], serialized['rbac_policy'])

    def test_rbac_filter(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)
        self.assertEqual(
            [
                {'term': {'tenant_id': TENANT1}},
                {'terms': {'members': [TENANT1, '*']}},
                {'term': {'router:external': True}},
                {'term': {'shared': True}}
            ],
            rbac_terms
        )

    def test_admin_only_fields(self):
        admin_only_fields = self.plugin.admin_only_fields
        self.assertEqual(['provider:*'], admin_only_fields)
