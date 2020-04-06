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

from elasticsearch import helpers
from searchlight.elasticsearch.plugins.neutron import\
    security_groups as securitygroups_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils

USER1 = uuidutils.generate_uuid()
ID1 = uuidutils.generate_uuid()
TENANT1 = uuidutils.generate_uuid()
_now_str = datetime.datetime.isoformat(datetime.datetime.utcnow())


def _secgroup_fixture(secgroup_id, tenant_id, name, **kwargs):
    fixture = {
        "security_group_rules": [{
            "remote_group_id": "855560aa-ff43-ee09-993e-6609342abccd",
            "direction": "ingress",
            "description": "",
            "protocol": "",
            "ethertype": "",
            "remote_ip_prefix": "",
            "port_range_max": "",
            "port_range_min": "",
            "security_group_id": "99347aac-4412-b809-5112-434901123a9c",
            "tenant_id": tenant_id,
            "id": secgroup_id,
        }],
        "id": secgroup_id,
        "tenant_id": tenant_id,
        "name": name,
        "description": ""
    }
    fixture.update(**kwargs)
    return fixture


def _secgrouprule_fixture(secgroup_id, tenant_id, **kwargs):
    fixture = {
        "security_group_rule": {
            "remote_group_id": "855560aa-ff43-ee09-993e-6609342abccd",
            "direction": "ingress",
            "protocol": "ipv4",
            "description": "",
            "ethertype": "",
            "remote_ip_prefix": "",
            "port_range_max": "",
            "port_range_min": "",
            "security_group_id": secgroup_id,
            "tenant_id": tenant_id,
            "id": secgroup_id,
        }
    }
    fixture.update(**kwargs)
    return fixture


class TestSecurityGroupLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSecurityGroupLoaderPlugin, self).setUp()
        self.plugin = securitygroups_plugin.SecurityGroupIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        """Create a security group to test data serialization. """
        self.security_group = _secgroup_fixture(secgroup_id=ID1,
                                                tenant_id=TENANT1,
                                                name="test-secgroup")

    def test_document_type(self):
        self.assertEqual('OS::Neutron::SecurityGroup',
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
            set(['security_group.create.end',
                 'security_group.delete.end',
                 'security_group_rule.create.end',
                 'security_group_rule.delete.end']),
            set(handler.get_event_handlers().keys())
        )

    def test_rule_update_exception(self):
        # Set up the return documents.
        payload = _secgrouprule_fixture(ID1, TENANT1)
        doc = {'_source': {'security_group_rules': [], 'id': 1},
               '_version': 1}

        handler = self.plugin.get_notification_handler()
        with mock.patch.object(self.plugin.index_helper,
                               'get_document') as mock_get:
            with mock.patch.object(self.plugin.index_helper,
                                   'save_document') as mock_save:
                mock_get.return_value = doc
                exc_obj = helpers.BulkIndexError(
                    "Version conflict", [{'index': {
                        "_id": "1", "error": "Some error", "status": 409}}]
                )

                # 1 retry (exception).
                mock_save.side_effect = [exc_obj, {}]
                handler.create_or_update_rule(
                    'security_group_rule.create.end', payload, None)
                # 1 retry +  1 success = 2 calls.
                self.assertEqual(2, mock_get.call_count)
                self.assertEqual(2, mock_save.call_count)

                # 24 retries (exceptions) that exceed the retry limit.
                # Not all retries will be used.
                mock_get.reset_mock()
                mock_save.reset_mock()
                mock_save.side_effect = [exc_obj, exc_obj, exc_obj, exc_obj,
                                         exc_obj, exc_obj, exc_obj, exc_obj,
                                         exc_obj, exc_obj, exc_obj, exc_obj,
                                         exc_obj, exc_obj, exc_obj, exc_obj,
                                         exc_obj, exc_obj, exc_obj, exc_obj,
                                         exc_obj, exc_obj, exc_obj, exc_obj,
                                         {}]
                handler.create_or_update_rule(
                    'security_group_rule.create.end', payload, None)
                # Verified we bailed out after 20 retires.
                self.assertEqual(20, mock_get.call_count)
                self.assertEqual(20, mock_save.call_count)

    def test_rule_delete_exception(self):
        # Set up the return documents.
        payload = {'security_group_rule_id': ID1}
        doc_get = {'_source': {'security_group_rules': [], 'id': 1},
                   '_version': 1}
        doc_nest = {'hits': {'hits': [{
                    '_id': 123456789,
                    '_source': {'security_group_rules': []},
                    '_version': 1}]}}

        handler = self.plugin.get_notification_handler()
        with mock.patch.object(self.plugin.index_helper,
                               'get_docs_by_nested_field') as mo_nest:
            with mock.patch.object(self.plugin.index_helper,
                                   'get_document') as mock_get:
                with mock.patch.object(self.plugin.index_helper,
                                       'save_document') as mock_save:
                    mo_nest.return_value = doc_nest
                    mock_get.return_value = doc_get
                    exc_obj = helpers.BulkIndexError(
                        "Version conflict", [{'index': {
                            "_id": "1", "error": "Some error", "status": 409}}]
                    )

                    # 1 retry (exception).
                    mock_save.side_effect = [exc_obj, {}]
                    handler.delete_rule(
                        'security_group_rule.delete.end', payload, None)
                    # 1 retry +  1 success = 2 calls.
                    self.assertEqual(1, mo_nest.call_count)
                    self.assertEqual(1, mock_get.call_count)
                    self.assertEqual(2, mock_save.call_count)

                    # 24 retries (exceptions) that exceed the retry limit.
                    # Not all retries will be used.
                    mo_nest.reset_mock()
                    mock_get.reset_mock()
                    mock_save.reset_mock()
                    mock_save.side_effect = [exc_obj, exc_obj, exc_obj,
                                             exc_obj, exc_obj, exc_obj,
                                             exc_obj, exc_obj, exc_obj,
                                             exc_obj, exc_obj, exc_obj,
                                             exc_obj, exc_obj, exc_obj,
                                             exc_obj, exc_obj, exc_obj,
                                             exc_obj, exc_obj, exc_obj,
                                             exc_obj, exc_obj, exc_obj,
                                             {}]
                    handler.delete_rule(
                        'security_group_rule.delete.end', payload, None)
                    # Verified we bailed out after 20 retires.
                    self.assertEqual(1, mo_nest.call_count)
                    self.assertEqual(20, mock_get.call_count)
                    self.assertEqual(20, mock_save.call_count)

    @mock.patch('searchlight.elasticsearch.plugins.utils.get_now_str')
    def test_serialize(self, mock_now):
        """Serializing the Security Group data will result in two new fields
           added to the record: project_id (copied from tenant_id) and
           updated_id (set to now_str). Verify this is done correctly.
        """
        mock_now.return_value = _now_str

        serialized = self.plugin.serialize(self.security_group)
        self.assertEqual(TENANT1, serialized['project_id'])
        self.assertEqual(_now_str, serialized['updated_at'])
