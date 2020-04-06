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

from unittest import mock
import webob

from searchlight.api.v1 import search
from searchlight.common import utils
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils

from searchlight.api import policy


REPO_SEARCH = 'searchlight.elasticsearch.CatalogSearchRepo.search'


class TestSearchPolicy(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSearchPolicy, self).setUp()
        self.enforcer = policy.Enforcer()
        self.enforcer.load_rules()

    def test_admin_or_owner(self):
        """Since this a commonly used rule, check that it works"""
        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'admin_or_owner': 'role:admin or project_id:%(project_id)s',
            'test_rule': 'rule:admin_or_owner'
        }))

        request = unit_test_utils.get_fake_request(is_admin=False)
        self.assertTrue(self.enforcer.check(request.context, 'test_rule',
                                            request.context.policy_target))

        request = unit_test_utils.get_fake_request(is_admin=False)
        self.assertFalse(self.enforcer.check(request.context, 'test_rule',
                                             {}))

        request = unit_test_utils.get_fake_request(is_admin=True)
        self.assertTrue(self.enforcer.check(request.context, 'test_rule',
                                            {}))

    def test_context_policy_target(self):
        request = unit_test_utils.get_fake_request()
        expected = {'user_id': unit_test_utils.SOMEUSER,
                    'project_id': unit_test_utils.SOMETENANT,
                    'tenant_id': unit_test_utils.SOMETENANT}
        self.assertEqual(expected, request.context.policy_target)

    def test_search_policy(self):
        request = unit_test_utils.get_fake_request()
        search_repo = mock.Mock()
        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            repo = policy.CatalogSearchRepoProxy(search_repo, request.context,
                                                 self.enforcer)
            repo.search()
            mock_enforce.assert_called_with(request.context,
                                            'search:query',
                                            request.context.policy_target)

    def test_plugin_policy(self):
        request = unit_test_utils.get_fake_request()
        search_repo = mock.Mock()
        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            repo = policy.CatalogSearchRepoProxy(search_repo, request.context,
                                                 self.enforcer)
            repo.plugins_info()
            mock_enforce.assert_called_with(request.context,
                                            'search:plugins_info',
                                            request.context.policy_target)

    def test_facet_policy(self):
        request = unit_test_utils.get_fake_request()
        search_repo = mock.Mock()
        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            repo = policy.CatalogSearchRepoProxy(search_repo, request.context,
                                                 self.enforcer)
            repo.facets()
            mock_enforce.assert_called_with(request.context,
                                            'search:facets',
                                            request.context.policy_target)

    @mock.patch('searchlight.api.v1.search.' +
                'RequestDeserializer._get_request_body')
    def test_search_resource_policy_checks(self, mock_request_body):
        request = unit_test_utils.get_fake_request()
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        with mock.patch.object(self.enforcer, 'check') as mock_enforce:
            mock_request_body.return_value = {'type': 'OS::Nova::Server'}
            search_deserializer.search(request)
            mock_enforce.assert_called_with(request.context,
                                            'resource:OS::Nova::Server',
                                            request.context.policy_target)

    def test_plugins_info_resource_policy(self):
        request = unit_test_utils.get_fake_request()
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        with mock.patch.object(self.enforcer, 'check') as mock_enforce:
            search_deserializer.plugins_info(request)
            self.assertIn(mock.call(request.context,
                                    'resource:OS::Nova::Server',
                                    request.context.policy_target),
                          mock_enforce.mock_calls)
            self.assertIn(mock.call(request.context,
                                    'resource:OS::Glance::Image',
                                    request.context.policy_target),
                          mock_enforce.mock_calls)
            self.assertEqual(len(utils.get_search_plugins()),
                             len(mock_enforce.call_args_list))

    def test_facets_resource_policy(self):
        request = unit_test_utils.get_fake_request()
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        with mock.patch.object(self.enforcer, 'check') as mock_enforce:
            search_deserializer.facets(request)
            self.assertIn(mock.call(request.context,
                                    'resource:OS::Nova::Server',
                                    request.context.policy_target),
                          mock_enforce.mock_calls)
            self.assertIn(mock.call(request.context,
                                    'resource:OS::Glance::Image',
                                    request.context.policy_target),
                          mock_enforce.mock_calls)
            self.assertEqual(len(utils.get_search_plugins()),
                             len(mock_enforce.call_args_list))

    def test_resource_policy_allowed(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server']

        self.assertEqual(
            types,
            search_deserializer._filter_types_by_policy(request.context, types)
        )

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image': '',
            'resource:OS::Nova::Server': ''
        }))

        self.assertEqual(
            types,
            search_deserializer._filter_types_by_policy(request.context, types)
        )

    def test_resource_policy_disallow_non_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server',
                 'OS::Glance::Metadef']

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image': 'role:admin'
        }))
        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types)
        self.assertEqual(set(['OS::Nova::Server', 'OS::Glance::Metadef']),
                         set(filtered_types))

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Nova::Server': 'role:admin'
        }))

        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types)
        self.assertEqual(['OS::Glance::Metadef'], filtered_types)

    def test_resource_policy_allows_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server']

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image': 'role:admin',
            'resource:OS::Nova::Server': 'role:admin'
        }))

        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types)
        self.assertEqual(types, filtered_types)

    def test_resource_policy_disallow(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server']

        # And try disabling access for everyone
        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image': '!'
        }))

        self.assertEqual(
            ['OS::Nova::Server'],
            search_deserializer._filter_types_by_policy(request.context, types)
        )

        # Same for admin
        request = unit_test_utils.get_fake_request(is_admin=False)
        self.assertEqual(
            ['OS::Nova::Server'],
            search_deserializer._filter_types_by_policy(request.context, types)
        )

    def test_policy_all_disallowed(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        types = ['OS::Glance::Image']
        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image': '!',
            'resource:OS::Nova::Server': '!',
        }))

        expected_message = (
            "There are no resource types accessible to you to serve "
            "your request. You do not have access to the following "
            "resource types: OS::Glance::Image")
        self.assertRaisesRegex(
            webob.exc.HTTPForbidden, expected_message,
            search_deserializer._filter_types_by_policy,
            request.context, types)

        types = ['OS::Glance::Image', 'OS::Nova::Server']
        expected_message = (
            "There are no resource types accessible to you to serve "
            "your request. You do not have access to the following "
            "resource types: OS::Glance::Image, OS::Nova::Server")
        self.assertRaisesRegex(
            webob.exc.HTTPForbidden, expected_message,
            search_deserializer._filter_types_by_policy,
            request.context, types)

    def test_search_service_policies(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        types = ['OS::Glance::Image', 'OS::Nova::Server']
        glance_enforce = mock.Mock()
        nova_enforce = mock.Mock()
        glance_enforce.enforce.return_value = False
        nova_enforce.enforce.return_value = True
        service_enforcers = {
            'image': glance_enforce,
            'compute': nova_enforce
        }

        expect_creds = {
            'tenant_id': request.context.tenant,
            'project_id': request.context.tenant,
            'user_id': request.context.user,
            'roles': ['member'],
            'is_admin_project': True,
            'is_admin': False,
            'domain_id': None,
            'user_domain_id': None,
            'project_domain_id': None,
            'service_user_id': None,
            'service_user_domain_id': None,
            'service_project_id': None,
            'service_project_domain_id': None,
            'service_roles': [],
            'system_scope': None
        }

        fake_target = {
            'user_id': request.context.user,
            'project_id': request.context.tenant,
            'tenant_id': request.context.tenant
        }

        with mock.patch('searchlight.service_policies._get_enforcers',
                        return_value=service_enforcers):
            filtered_types = search_deserializer._filter_types_by_policy(
                request.context, types)
            self.assertEqual(['OS::Nova::Server'], filtered_types)
            glance_enforce.enforce.assert_called_with(
                'get_images', fake_target, expect_creds)
            nova_enforce.enforce.assert_called_with(
                'os_compute_api:servers:index', fake_target, expect_creds)

    @mock.patch('searchlight.api.v1.search.' +
                'RequestDeserializer._get_request_body')
    def test_aggregation_policy(self, mock_request_body):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            mock_request_body.return_value = {
                'query': {'match_all': {}},
                'aggregations': {'terms': {'field': 'some_field'}}
            }
            search_deserializer.search(request)
            mock_enforce.assert_called_with(request.context,
                                            'search:query:aggregations',
                                            request.context.policy_target)
