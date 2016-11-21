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

import copy

from oslo_utils import uuidutils

from searchlight.tests import functional


MATCH_ALL = {"query": {"match_all": {}}}

OWNER1 = uuidutils.generate_uuid()
NETWORK_TENANT_ID = '8eaac046b2c44ab99246cb0850c7f06d'


class TestSearchListenerBase(functional.FunctionalTest):

    def __init__(self, *args, **kwargs):
        super(TestSearchListenerBase, self).__init__(*args, **kwargs)

    def _send_event_to_listener(self, event, index_to_flush):
        event = copy.deepcopy(event)
        self.notification_endpoint.info(
            event['ctxt'],
            event['publisher_id'],
            event['event_type'],
            event['payload'],
            event['metadata']
        )
        self._flush_elasticsearch(index_to_flush)

    def _verify_event_processing(self, event, count=1, owner=None):
        if not owner:
            payload = event['payload']
            # Try several keys in the payload to extract an owner
            owner = payload.get(
                'owner',
                payload.get('project_id',
                            payload.get('tenant_id')))
            if not owner:
                raise Exception("No project/owner info found in payload")

        response, json_content = self._search_request(
            MATCH_ALL,
            owner, role="admin")
        self.assertEqual(count, json_content['hits']['total'])
        return json_content

    def _verify_result(self, event, verification_keys, result_json,
                       inner_key=None):
        expected = event['payload']
        if inner_key:
            expected = expected[inner_key]

        result = result_json['hits']['hits'][0]['_source']
        for key in verification_keys:
            self.assertEqual(expected[key], result[key])
