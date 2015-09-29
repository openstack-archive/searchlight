# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

import httplib2
import six

from oslo_serialization import jsonutils


def _headers(custom_headers={}):
        base_headers = {
            "X-Identity-Status": "Confirmed",
            "X-Auth-Token": "932c5c84-02ac-4fe5-a9ba-620af0e2bb96",
            "X-User-Id": "f9a41d13-0c13-47e9-bee2-ce4e8bfe958e",
            "X-Roles": "member",
            "Content-Type": "application/json"
        }
        base_headers.update(custom_headers)
        return base_headers


def search_request(base_url, body, tenant, role="member", decode_json=True):
    """Conduct a search against all elasticsearch indices unless specified
    in `body`. Returns the response and json-decoded content.
    """

    custom_headers = {
        "X-Tenant-Id": tenant,
        "X-Roles": role,
    }
    headers = _headers(custom_headers)

    http = httplib2.Http()
    response, content = http.request(
        base_url + "/search",
        "POST",
        headers=headers,
        body=jsonutils.dumps(body)
    )
    if response.status != 200:
        raise Exception(content)

    if decode_json:
        content = jsonutils.loads(content)
    return response, content


def get_json(es_response):
    """Parse the _source from the elasticsearch hits"""

    if six.PY2:
        if isinstance(es_response, basestring):
            es_response = jsonutils.loads(es_response)
    else:
        if isinstance(es_response, str):
            es_response = jsonutils.loads(es_response)
    return es_response
