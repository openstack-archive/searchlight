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
    containers as containers_plugin
import searchlight.tests.utils as test_utils


now_epoch_time = time.time()
now_utc = datetime.datetime.fromtimestamp(now_epoch_time).\
    strftime('%Y-%m-%dT%H:%M:%SZ')


USER1 = "27f4d76b-be62-4e4e-aa33bb11cc55"

ACCOUNT_ID1 = "488ac936-663e-4e5c-537d-986021b32c4b"
ACCOUNT_ID2 = "7554da43-6443-acdf-deac-3425223cdada"
ACCOUNT_ID3 = "30754354-ca43-124b-12b5-789234bcdefa'"

AUTH_PREFIX = "AUTH_"

CONTAINER1 = "Container1"
CONTAINER2 = "Container2"
CONTAINER_ID1 = ACCOUNT_ID1 + swift_plugin.ID_SEP + CONTAINER1
CONTAINER_ID2 = ACCOUNT_ID2 + swift_plugin.ID_SEP + CONTAINER2

X_CONTAINER_META_KEY1 = 'x-container-meta-key1'
X_CONTAINER_META_VALUE1 = 'x-container-meta-value1'

X_CONTAINER_META_KEY2 = 'x-container-meta-key2'
X_CONTAINER_META_VALUE2 = 'x-container-meta-value2'

TENANT1 = "15b9a454cee34dbe9933ad575a0a6930"
TENANT2 = "a7ba963f71bb43818f631febbc9df8e6"
DOMAIN_ID = "default"

DATETIME = datetime.datetime(2016, 2, 21, 4, 41, 33, 325314)
DATE1 = utils.isotime(DATETIME)


def _container_fixture(container_id, container_name, account,
                       account_id, read_acl, **kwargs):
    fixture = {
        "id": container_id,
        "name": container_name,
        "account": account,
        "account_id": account_id,
        "x-container-read": read_acl,
        'x-timestamp': now_epoch_time
    }
    fixture.update(kwargs)
    return fixture


def _notification_container_fixture(account_id, **kwargs):
    metadata = kwargs.pop('meta', {})
    notification = {
        'account': account_id,
        'project_name': None,
        'container': None,
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


class TestSwiftContainerPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSwiftContainerPlugin, self).setUp()
        self.plugin = containers_plugin.ContainerIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.container1 = _container_fixture(
            container_id=CONTAINER_ID1, container_name=CONTAINER1,
            account='test-account1', account_id=ACCOUNT_ID1, read_acl=None)
        self.container2 = _container_fixture(
            container_id=CONTAINER_ID2, container_name=CONTAINER2,
            account='test-account2', account_id=ACCOUNT_ID1,
            read_acl=ACCOUNT_ID2 + ":*",
            **{X_CONTAINER_META_KEY1: X_CONTAINER_META_VALUE1}
        )
        self.container3 = _container_fixture(
            container_id=CONTAINER_ID1, container_name=CONTAINER1,
            account='test-account3', account_id=ACCOUNT_ID2,
            read_acl=ACCOUNT_ID3 + ":*" + USER1,
            **{X_CONTAINER_META_KEY1: X_CONTAINER_META_VALUE1,
               X_CONTAINER_META_KEY2: X_CONTAINER_META_VALUE2})
        self.containers = [self.container1, self.container2, self.container3]

    def test_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Swift::Container',
                         self.plugin.get_document_type())

    def test_admin_only_fields(self):
        admin_only_fields = self.plugin.admin_only_fields
        self.assertEqual(['x-container-write',
                          'x-container-sync-key',
                          'x-container-sync-to',
                          'x-container-meta-temp-url-key',
                          'x-container-meta-temp-url-key-2'],
                         admin_only_fields)

    def test_serialize(self):
        serialized = self.plugin.serialize(self.container1)

        self.assertEqual(CONTAINER_ID1, serialized['id'])
        self.assertEqual(CONTAINER1, serialized['name'])
        self.assertEqual(ACCOUNT_ID1, serialized['account_id'])
        self.assertEqual('test-account1', serialized['account'])

        serialized = self.plugin.serialize(self.container2)
        self.assertEqual(X_CONTAINER_META_VALUE1,
                         serialized[X_CONTAINER_META_KEY1])
        self.assertEqual(ACCOUNT_ID2 + ":*", serialized['x-container-read'])

        serialized = self.plugin.serialize(self.container3)
        self.assertEqual(X_CONTAINER_META_VALUE1,
                         serialized[X_CONTAINER_META_KEY1])
        self.assertEqual(X_CONTAINER_META_VALUE2,
                         serialized[X_CONTAINER_META_KEY2])

    def test_swift_account_notification_serialize(self):
        notification = _notification_container_fixture(
            swift_plugin.AUTH_PREFIX + ACCOUNT_ID1,
            container=CONTAINER1,
            project_name='admin',
            project_domain_id='default',
            project_id=ACCOUNT_ID1,
            updated_at=DATE1,
        )

        expected = {
            'id': CONTAINER_ID1,
            'name': CONTAINER1,
            'account': 'admin',
            'account_id': ACCOUNT_ID1,
            'updated_at': DATE1,
            'x-container-read': None
        }

        serialized = swift_plugin.serialize_swift_container_notification(
            notification)
        self.assertEqual(expected, serialized)
