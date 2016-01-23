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

import searchlight.elasticsearch.plugins.swift as swift_plugin
from searchlight.elasticsearch.plugins.swift import\
    objects as objects_plugin
import searchlight.tests.utils as test_utils


now_epoch_time = time.time()
created_time = now_epoch_time - 3
updated_time = now_epoch_time
updated_time_in_fmt = datetime.datetime.fromtimestamp(updated_time).\
    strftime('%a, %d %b %Y %H:%M:%S GMT')
updated_time_out_fmt = datetime.datetime.fromtimestamp(updated_time).\
    strftime('%Y-%m-%dT%H:%M:%SZ')
created_time_utc = datetime.datetime.fromtimestamp(created_time).\
    strftime('%Y-%m-%dT%H:%M:%SZ')

USER1 = "27f4d76b-be62-4e4e-aa33bb11cc55"

ACCOUNT_ID1 = "488ac936-663e-4e5c-537d-986021b32c4b"
CONTAINER1 = "Container1"
CONTAINER_ID1 = ACCOUNT_ID1 + swift_plugin.ID_SEP + CONTAINER1
OBJECT1 = "Object1"
OBJECT2 = "Object2"
OBJECT_ID1 = CONTAINER_ID1 + swift_plugin.ID_SEP + OBJECT1
OBJECT_ID2 = CONTAINER_ID1 + swift_plugin.ID_SEP + OBJECT2

X_OBJECT_META_KEY1 = 'x-object-meta-key1'
X_OBJECT_META_VALUE1 = 'x-object-meta-value1'

X_OBJECT_META_KEY2 = 'x-object-meta-key2'
X_OBJECT_META_VALUE2 = 'x-object-meta-value2'

TENANT1 = "15b9a454cee34dbe9933ad575a0a6930"


def _object_fixture(object_id, object_name, container_id, container_name,
                    account, account_id, **kwargs):
    fixture = {
        "id": object_id,
        "name": object_name,
        "account": account,
        "account_id": account_id,
        "container": container_name,
        "container_id": container_id,
        'x-timestamp': created_time,
        'last-modified': updated_time_in_fmt
    }
    fixture.update(kwargs)
    return fixture


class TestSwiftObjectPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestSwiftObjectPlugin, self).setUp()
        self.plugin = objects_plugin.ObjectIndex()
        self._create_fixtures()

    def _create_fixtures(self):
        self.object1 = _object_fixture(
            object_id=OBJECT_ID1, object_name=OBJECT1,
            container_id=CONTAINER_ID1, container_name=CONTAINER1,
            account='test-account1', account_id=ACCOUNT_ID1,
            **{"content-type": "text/plain", "content-length": 1050})
        self.object2 = _object_fixture(
            object_id=OBJECT_ID2, object_name=OBJECT2,
            container_id=CONTAINER_ID1, container_name=CONTAINER1,
            account='test-account1', account_id=ACCOUNT_ID1,
            **{"content-type": "text/plain", "content-length": 1050,
               X_OBJECT_META_KEY1: X_OBJECT_META_VALUE1,
               X_OBJECT_META_KEY2: X_OBJECT_META_VALUE2})
        self.objects = [self.object1, self.object2]

    def test_index_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Swift::Object',
                         self.plugin.get_document_type())

    def test_admin_only_fields(self):
        admin_only_fields = self.plugin.admin_only_fields
        self.assertEqual([], admin_only_fields)

    def test_serialize(self):
        serialized = self.plugin.serialize(self.object1)

        self.assertEqual(OBJECT_ID1, serialized['id'])
        self.assertEqual(OBJECT1, serialized['name'])
        self.assertEqual(ACCOUNT_ID1, serialized['account_id'])
        self.assertEqual('test-account1', serialized['account'])
        self.assertEqual(CONTAINER_ID1, serialized['container_id'])
        self.assertEqual(CONTAINER1, serialized['container'])
        self.assertEqual(created_time_utc, serialized['created_at']),
        self.assertEqual(updated_time_out_fmt, serialized['updated_at'])
        self.assertEqual("text/plain", serialized['content_type'])
        self.assertEqual(1050, serialized['content_length'])

        serialized = self.plugin.serialize(self.object2)
        self.assertEqual(X_OBJECT_META_VALUE1,
                         serialized[X_OBJECT_META_KEY1])
        self.assertEqual(X_OBJECT_META_VALUE2,
                         serialized[X_OBJECT_META_KEY2])
