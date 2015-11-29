# Copyright 2012 OpenStack Foundation.
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

from oslo_serialization import jsonutils
import webob

from searchlight.api import versions
import searchlight.tests.utils as test_utils


class VersionsTest(test_utils.BaseTestCase):

    """Test the version information returned from the API service."""

    def test_get_version_list(self):
        req = webob.Request.blank('/', base_url='http://127.0.0.1:9393/')
        req.accept = 'application/json'
        self.config(bind_host='127.0.0.1', bind_port=9393, group='api')
        res = versions.Controller().index(req)
        self.assertEqual(300, res.status_int)
        self.assertEqual('application/json', res.content_type)
        results = jsonutils.loads(res.body)['versions']
        expected = [
            {
                'id': 'v1.0',
                'status': 'CURRENT',
                'links': [{'rel': 'self',
                           'href': 'http://127.0.0.1:9393/v1/'}],
            },
        ]
        self.assertEqual(expected, results)
