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

import mock
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

    def test_default_rules(self):
        # Establish some sane defaults for use by these tests
        self.assertTrue(self.enforcer.use_conf)

        request = unit_test_utils.get_fake_request(is_admin=False)
        self.assertTrue(self.enforcer.enforce(request.context, 'default', {}))
        self.assertTrue(self.enforcer.enforce(request.context, 'query', {}))
        self.assertTrue(self.enforcer.enforce(request.context, 'facets', {}))
        self.assertTrue(self.enforcer.enforce(request.context,
                                              'plugins_info', {}))

        self.assertNotIn('resource:OS::Glance::Image:allow',
                         self.enforcer.rules)
        self.assertNotIn('resource:OS::Glance::Image:query',
                         self.enforcer.rules)
        self.assertNotIn('resource:OS::Nova::Server:allow',
                         self.enforcer.rules)
        self.assertNotIn('resource:OS::Nova::Server:query',
                         self.enforcer.rules)

    def test_search_policy(self):
        request = unit_test_utils.get_fake_request()
        search_repo = mock.Mock()
        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            repo = policy.CatalogSearchRepoProxy(search_repo, request.context,
                                                 self.enforcer)
            repo.search()
            mock_enforce.assert_called_with(request.context, 'query', {})

    def test_plugin_policy(self):
        request = unit_test_utils.get_fake_request()
        search_repo = mock.Mock()
        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            repo = policy.CatalogSearchRepoProxy(search_repo, request.context,
                                                 self.enforcer)
            repo.plugins_info()
            mock_enforce.assert_called_with(request.context,
                                            'plugins_info', {})

    def test_facet_policy(self):
        request = unit_test_utils.get_fake_request()
        search_repo = mock.Mock()
        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            repo = policy.CatalogSearchRepoProxy(search_repo, request.context,
                                                 self.enforcer)
            repo.facets()
            mock_enforce.assert_called_with(request.context, 'facets', {})

    @mock.patch('searchlight.api.v1.search.' +
                'RequestDeserializer._get_request_body')
    def test_search_resource_policy_checks(self, mock_request_body):
        request = unit_test_utils.get_fake_request()
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            mock_request_body.return_value = {'type': 'OS::Nova::Server'}
            search_deserializer.search(request)
            self.assertEqual(2, mock_enforce.call_count)
            mock_enforce.assert_has_calls([
                mock.call(request.context,
                          'resource:OS::Nova::Server:allow', {}),
                mock.call(request.context,
                          'resource:OS::Nova::Server:query', {})
            ])

    def test_plugins_info_resource_policy(self):
        request = unit_test_utils.get_fake_request()
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            search_deserializer.plugins_info(request)
            mock_enforce.assert_has_calls([
                mock.call(request.context,
                          'resource:OS::Nova::Server:allow', {}),
                mock.call(request.context,
                          'resource:OS::Nova::Server:plugins_info', {})
            ])

    def test_facets_resource_policy(self):
        request = unit_test_utils.get_fake_request()
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        with mock.patch.object(self.enforcer, 'enforce') as mock_enforce:
            search_deserializer.facets(request)
            mock_enforce.assert_has_calls([
                mock.call(request.context,
                          'resource:OS::Nova::Server:allow', {}),
                mock.call(request.context,
                          'resource:OS::Nova::Server:facets', {})
            ])

    def test_resource_policy_allowed(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server']

        self.assertEqual(
            types,
            search_deserializer._filter_types_by_policy(request.context,
                                                        types, "query"))

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image:allow': '',
            'resource:OS::Nova::Server:allow': ''
        }))

        self.assertEqual(
            types,
            search_deserializer._filter_types_by_policy(request.context,
                                                        types, "query"))

    def test_resource_policy_disallow_non_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server',
                 'OS::Glance::Metadef']

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image:allow': 'role:admin'
        }))
        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types, "query")
        self.assertEqual(set(['OS::Nova::Server', 'OS::Glance::Metadef']),
                         set(filtered_types))

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Nova::Server:query': 'role:admin'
        }))

        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types, "query")
        self.assertEqual(['OS::Glance::Metadef'], filtered_types)

    def test_resource_policy_allows_admin(self):
        request = unit_test_utils.get_fake_request(is_admin=True)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server']

        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image:allow': 'role:admin',
            'resource:OS::Nova::Server:query': 'role:admin'
        }))

        request = unit_test_utils.get_fake_request(is_admin=True)
        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types, "query")
        self.assertEqual(types, filtered_types)

    def test_resource_policy_disallow(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server']

        # And try disabling access for everyone
        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image:allow': '!'
        }))

        self.assertEqual(
            ['OS::Nova::Server'],
            search_deserializer._filter_types_by_policy(request.context,
                                                        types, "query"))

        # Same for admin
        request = unit_test_utils.get_fake_request(is_admin=False)
        self.assertEqual(
            ['OS::Nova::Server'],
            search_deserializer._filter_types_by_policy(request.context,
                                                        types, "query"))

    def test_policy_precedence(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Nova::Server', 'OS::Glance::Image']
        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Nova::Server:allow': '',
            'resource:OS::Nova::Server:query': '!'
        }))

        # Query should be disallowed by the specific policy
        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types, "query")
        self.assertEqual(['OS::Glance::Image'], filtered_types)

        # Facet should be allowed since there is no specific exclusion
        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types, "facets")
        self.assertEqual(set(['OS::Nova::Server', 'OS::Glance::Image']),
                         set(filtered_types))

    def test_faulty_policy_precedence(self):
        """Unfortunately the ordering that might make most sense isn't
        possible. Rules can only become more restrictive
         """
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)
        types = ['OS::Glance::Image', 'OS::Nova::Server']
        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image:allow': '!',
            'resource:OS::Glance::Image:query': ''
        }))

        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types, "facets")
        self.assertEqual(['OS::Nova::Server'], filtered_types)

        filtered_types = search_deserializer._filter_types_by_policy(
            request.context, types, "query")
        self.assertEqual(['OS::Nova::Server'], filtered_types)

    def test_policy_all_disallowed(self):
        request = unit_test_utils.get_fake_request(is_admin=False)
        search_deserializer = search.RequestDeserializer(
            utils.get_search_plugins(),
            policy_enforcer=self.enforcer)

        types = ['OS::Glance::Image']
        self.enforcer.add_rules(policy.policy.Rules.from_dict({
            'resource:OS::Glance::Image:allow': '!',
            'resource:OS::Nova::Server:allow': '!',
        }))

        expected_message = (
            "There are no resource types accessible to you to serve "
            "your request. You do not have access to the following "
            "resource types: OS::Glance::Image")
        self.assertRaisesRegexp(
            webob.exc.HTTPForbidden, expected_message,
            search_deserializer._filter_types_by_policy,
            request.context, types, "query")

        types = ['OS::Glance::Image', 'OS::Nova::Server']
        expected_message = (
            "There are no resource types accessible to you to serve "
            "your request. You do not have access to the following "
            "resource types: OS::Glance::Image, OS::Nova::Server")
        self.assertRaisesRegexp(
            webob.exc.HTTPForbidden, expected_message,
            search_deserializer._filter_types_by_policy,
            request.context, types, "query")
