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
    routers as routers_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


_now_str = utils.isotime(datetime.datetime.utcnow())
USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'
ID1 = "813dd936-663e-4e5b-877c-986021b73e2c"
NETID1 = "98dcb60c-59b9-4b3c-bf6a-b8504112e978"
TENANT1 = "8eaac046b2c44ab99246cb0850c7f06d"


def _router_fixture(router_id, tenant_id, name, **kwargs):
    fixture = {
        u'admin_state_up': True,
        u'availability_zone_hints': [],
        u'availability_zones': [],
        u'external_gateway_info': {
            u'enable_snat': True,
            u'external_fixed_ips': [{
                u'ip_address': u'172.25.0.2',
                u'subnet_id': u'8cbe9b71-ecf1-4355-b5ba-dee54ec88fa7'
            }, {
                u'ip_address': u'2001:db8::1',
                u'subnet_id': u'd7774648-ba81-477a-9329-2acc9a810e50'
            }],
            u'network_id': u'8891323e-bf5b-48d7-a75e-669af0608538'},
        u'id': router_id,
        u'name': name,
        u'routes': [],
        u'status': u'ACTIVE',
        u'tenant_id': tenant_id}
    fixture.update(**kwargs)
    return fixture


def _gateway_info(network_id, fixed_ips):
    return {
        u'enable_snat': True,
        u'external_fixed_ips': fixed_ips,
        u'network_id': network_id
    }


class TestRouterLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestRouterLoaderPlugin, self).setUp()
        self.plugin = routers_plugin.RouterIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.router1 = _router_fixture(router_id=ID1, network_id=NETID1,
                                       tenant_id=TENANT1, name="test-router-1")
        self.routers = [self.router1]

    def test_admin_only(self):
        self.assertEqual(['distributed', 'ha'], self.plugin.admin_only_fields)

    def test_document_type(self):
        self.assertEqual('OS::Neutron::Router',
                         self.plugin.get_document_type())

    def test_rbac_filter(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)
        self.assertEqual(
            [{"term": {"tenant_id": TENANT1}}],
            rbac_terms
        )

    def test_notification_events(self):
        handler = self.plugin.get_notification_handler()
        self.assertEqual(
            set(['router.create.end', 'router.update.end',
                 'router.delete.end']),
            set(handler.get_event_handlers().keys())
        )
