# Copyright 2015 Intel Corporation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import testtools

from searchlight.common.exception import SearchlightException
from searchlight.elasticsearch.plugins.base import NotificationBase


class TestExternalVersion(testtools.TestCase):

    def setUp(self):
        super(TestExternalVersion, self).setUp()
        self.payload = {'updated_at': '2015-12-15 06:40:55',
                        'created_at': '2015-12-12 06:40:55'}
        self.aware_payload = {'updated_at': '2015-12-15 06:40:55+0800',
                              'created_at': '2015-12-12 06:40:55+0800'}
        self.timestamp = '2015-12-15 06:40:55.012316'

    def get_interval(self, version1, version2):
        '''
            We're only interested in the resource data, not
            the messaging one
        '''
        return (version1 // 10 ** 9) - (version2 // 10 ** 9)

    def test_use_update_with_timestamp(self):
        version = NotificationBase.get_version(self.payload, self.timestamp)
        self.assertEqual(450161655161655012, version)
        self.assertGreater(version, 10 ** 17)

        aware_version = NotificationBase.get_version(self.aware_payload,
                                                     self.timestamp)
        self.assertEqual(450132855161655012, aware_version)
        self.assertEqual(18, len(str(aware_version)))

        self.assertEqual(self.get_interval(version, aware_version), 28800)

    def test_use_create_with_timestamp(self):
        self.payload.pop('updated_at')
        self.aware_payload.pop('updated_at')

        version = NotificationBase.get_version(self.payload, self.timestamp)
        self.assertEqual(449902455161655012, version)
        self.assertEqual(18, len(str(version)))

        aware_version = NotificationBase.get_version(self.aware_payload,
                                                     self.timestamp)
        self.assertEqual(449873655161655012, aware_version)
        self.assertEqual(18, len(str(aware_version)))

        self.assertEqual(self.get_interval(version, aware_version), 28800)

    def test_use_update_without_timestamp(self):
        version = NotificationBase.get_version(self.payload)
        self.assertEqual(450161655000000000, version)
        self.assertEqual(18, len(str(version)))

        aware_version = NotificationBase.get_version(self.aware_payload)
        self.assertEqual(450132855000000000, aware_version)
        self.assertEqual(18, len(str(aware_version)))

        self.assertEqual(self.get_interval(version, aware_version), 28800)

    def test_use_create_without_timestamp(self):
        self.payload.pop('updated_at')
        self.aware_payload.pop('updated_at')

        version = NotificationBase.get_version(self.payload)
        self.assertEqual(449902455000000000, version)
        self.assertEqual(18, len(str(version)))

        aware_version = NotificationBase.get_version(self.aware_payload)
        self.assertEqual(449873655000000000, aware_version)
        self.assertEqual(18, len(str(aware_version)))

        self.assertEqual(self.get_interval(version, aware_version), 28800)

    def test_exception_without_update(self):
        self.assertRaises(SearchlightException,
                          NotificationBase.get_version, {})
        self.assertRaises(SearchlightException,
                          NotificationBase.get_version, {}, self.timestamp
                          )
