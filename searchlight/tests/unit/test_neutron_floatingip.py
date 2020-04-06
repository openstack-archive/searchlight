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
from unittest import mock

from oslo_utils import uuidutils

from searchlight.elasticsearch.plugins.neutron import\
    floatingips as floatingips_plugin

import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'
TENANT1 = u'8eaac046b2c44ab99246cb0850c7f06d'
NETWORK1 = u'bc0adf22-3aef-4e7b-8b99-12670b5a76b5'

_now_str = datetime.datetime.isoformat(datetime.datetime.utcnow())

FIP_ID1 = uuidutils.generate_uuid()
FIP_ID2 = uuidutils.generate_uuid()

PORT_ID = uuidutils.generate_uuid()


def _create_fixture(fip_id, tenant_id, network_id, ip_addr, **kwargs):
    fixture = {
        "router_id": uuidutils.generate_uuid(),
        "status": "ACTIVE" if "fixed_ip_address" in kwargs else "DOWN",
        "description": "",
        "dns_name": "",
        "dns_domain": "",
        "floating_network_id": network_id,
        "fixed_ip_address": None,
        "floating_ip_address": ip_addr,
        "tenant_id": tenant_id,
        "port_id": None,
        "id": fip_id
    }
    fixture.update(**kwargs)
    return fixture


class TestFloatingIPLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestFloatingIPLoaderPlugin, self).setUp()
        self.plugin = floatingips_plugin.FloatingIPIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.unassociated = _create_fixture(FIP_ID1, TENANT1,
                                            NETWORK1, '172.0.0.15')
        self.associated = _create_fixture(FIP_ID2, TENANT1,
                                          NETWORK1, '172.0.0.25',
                                          port_id=PORT_ID,
                                          fixed_ip_address='192.0.9.50')

    def test_document_type(self):
        self.assertEqual("OS::Neutron::FloatingIP",
                         self.plugin.get_document_type())

    def test_parent_type(self):
        # Explicitly not setting a parent since there'll only ever be one
        self.assertIsNone(self.plugin.parent_plugin_type())

    def test_rbac_filter(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)

        expected = [{"term": {"tenant_id": TENANT1}}]
        self.assertEqual(expected, rbac_terms)

    @mock.patch('searchlight.elasticsearch.plugins.utils.get_now_str')
    def test_serialize(self, mock_now):
        mock_now.return_value = _now_str

        serialized = self.plugin.serialize(self.unassociated)

        # project id should get copied from tenant_id
        self.assertEqual(TENANT1, serialized['project_id'])
        # Expect updated_at date to be generated
        self.assertEqual(_now_str, serialized['updated_at'])
