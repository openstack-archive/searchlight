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

import webob

from searchlight.api.middleware import context
import searchlight.context
import searchlight.tests.utils as test_utils


class TestContextMiddleware(test_utils.BaseTestCase):
    def test_response(self):
        middleware = context.ContextMiddleware(None)
        req = webob.Request.blank('/')
        req.context = searchlight.context.RequestContext()
        request_id = req.context.request_id

        resp = webob.Response()
        resp.request = req
        middleware.process_response(resp)
        self.assertEqual(request_id, resp.headers['x-openstack-request-id'])
        resp_req_id = resp.headers['x-openstack-request-id']
        # Validate that request-id do not starts with 'req-req-'
        self.assertFalse(resp_req_id.startswith('req-req-'))
        self.assertTrue(resp_req_id.startswith('req-'))

    def test_is_admin_project(self):
        middleware = context.ContextMiddleware(None)
        req = webob.Request.blank('/')
        req_context = middleware._get_authenticated_context(req)
        self.assertTrue(req_context.is_admin_project)

        req = webob.Request.blank('/', headers={'X-Is-Admin-Project': 'True'})
        req_context = middleware._get_authenticated_context(req)
        self.assertTrue(req_context.is_admin_project)

        req = webob.Request.blank('/', headers={'X-Is-Admin-Project': 'False'})
        req_context = middleware._get_authenticated_context(req)
        self.assertFalse(req_context.is_admin_project)
