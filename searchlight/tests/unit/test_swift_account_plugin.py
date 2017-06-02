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
import time

from searchlight.common import utils
import searchlight.elasticsearch.plugins.swift as swift_plugin
from searchlight.elasticsearch.plugins.swift import\
    accounts as accounts_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


now_epoch_time = time.time()
now_utc = datetime.datetime.fromtimestamp(now_epoch_time)\
    .strftime('%Y-%m-%dT%H:%M:%SZ')


USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'
ID1 = "AUTH_488ac936-663e-4e5c-537d-986021b32c4b"
ID2 = "AUTH_7554da43-6443-acdf-deac-3425223cdada"
ID3 = "AUTH_30754354-ca43-124b-12b5-789234bcdefa'"

AUTH_PREFIX = "AUTH_"

X_ACCOUNT_META_KEY1 = 'x-account-meta-key1'
X_ACCOUNT_META_VALUE1 = 'x-account-meta-value1'

X_ACCOUNT_META_KEY2 = 'x-account-meta-key2'
X_ACCOUNT_META_VALUE2 = 'x-account-meta-value2'

TENANT1 = "15b9a454cee34dbe9933ad575a0a6930"
DOMAIN_ID = "default"

DATETIME = datetime.datetime(2016, 2, 20, 1, 13, 24, 215337)
DATE1 = utils.isotime(DATETIME)


def _account_fixture(account_id, domain_id, name, **kwargs):
    fixture = {
        "id": account_id,
        "name": name,
        "x-account-project-domain-id": domain_id,
        'x-timestamp': now_epoch_time
    }
    fixture.update(kwargs)
    return fixture


def _notification_account_fixture(account_id, **kwargs):
    metadata = kwargs.pop('meta', {})
    notification = {
        'account': account_id,
        'project_name': None,
        'updated_at': DATE1,
        'project_domain_name': None,
        'x-trans-id': None,
        'project_id': None,
        'project_domain_id': None
    }
    for k, v in kwargs.items():
        if k in notification:
            notification[k] = v
    for k, v in metadata.items():
        notification[k] = v
    return notification


class TestSwiftAccountPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSwiftAccountPlugin, self).setUp()
        self.plugin = accounts_plugin.AccountIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.account1 = _account_fixture(
            account_id=ID1, domain_id=DOMAIN_ID, name="test-account1")
        self.account2 = _account_fixture(
            account_id=ID2, domain_id=DOMAIN_ID, name="test-account1",
            **{X_ACCOUNT_META_KEY1: X_ACCOUNT_META_VALUE1})
        self.account3 = _account_fixture(
            account_id=ID3, domain_id=DOMAIN_ID, name="test-account1",
            **{X_ACCOUNT_META_KEY1: X_ACCOUNT_META_VALUE1,
                X_ACCOUNT_META_KEY2: X_ACCOUNT_META_VALUE2})
        self.accounts = [self.account1, self.account2, self.account3]

    def test_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Swift::Account',
                         self.plugin.get_document_type())

    def test_rbac_filter(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        rbac_terms = self.plugin._get_rbac_field_filters(fake_request.context)
        self.assertEqual(
            [{"term": {"id": AUTH_PREFIX + TENANT1}}],
            rbac_terms
        )

    def test_admin_only_fields(self):
        admin_only_fields = self.plugin.admin_only_fields
        self.assertEqual(['x-account-meta-temp-url-key',
                          'x-account-meta-temp-url-key-2',
                          'x-account-access-control'], admin_only_fields)

    def test_serialize(self):
        serialized = self.plugin.serialize(self.account1)

        self.assertEqual(ID1, serialized['id'])
        self.assertEqual('test-account1', serialized['name'])
        self.assertEqual(DOMAIN_ID, serialized['domain_id'])
        self.assertEqual(now_utc, serialized['created_at'])

        serialized = self.plugin.serialize(self.account2)
        self.assertEqual(X_ACCOUNT_META_VALUE1,
                         serialized[X_ACCOUNT_META_KEY1])

        serialized = self.plugin.serialize(self.account3)
        self.assertEqual(X_ACCOUNT_META_VALUE1,
                         serialized[X_ACCOUNT_META_KEY1])
        self.assertEqual(X_ACCOUNT_META_VALUE2,
                         serialized[X_ACCOUNT_META_KEY2])

    def test_swift_account_notification_serialize(self):
        notification = _notification_account_fixture(
            ID1,
            project_name='admin',
            project_id=ID1,
            project_domain_id='default',
            updated_at=DATE1,
        )

        expected = {
            'id': ID1,
            'name': 'admin',
            'updated_at': DATE1,
            'domain_id': 'default'
        }

        serialized = swift_plugin.serialize_swift_account_notification(
            notification)
        self.assertEqual(expected, serialized)
