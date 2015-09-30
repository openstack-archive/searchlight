# Copyright 2015 Hewlett-Packard Corporation
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

import datetime
import mock

from searchlight.elasticsearch.plugins.designate import zones as zones_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


now = datetime.datetime.utcnow()
five_mins = datetime.timedelta(minutes=5)
updated_now = now.strftime('%Y-%m-%dT%H:%M:%SZ')
created_now = (now - five_mins).strftime('%Y-%m-%dT%H:%M:%SZ')

USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'

TENANT1 = u'4d64ac83-87af-4d2a-b884-cc42c3e8f2c0'
TENANT2 = u'c6993374-7c4b-4f18-b317-85e3acdfd259'

# Zone ids
ID1 = u'9b4c2de5-dead-0000-beef-e3b99695aa69'
ID2 = u'0c3dae67-c4d3-42d6-9d8d-98da56321bca'
ID3 = u'7c3df12a-42d6-9d8d-c4d3-98da56321999'


def _zone_fixture(zone_id, tenant_id, name, **kwargs):
    zone = {
        'tenant_id': tenant_id,
        'name': name,
        'status': 'pending',
        'created_at': created_now,
        'updated_at': updated_now
    }
    zone.update(**kwargs)
    return zone


class TestZonePlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestZonePlugin, self).setUp()
        self.plugin = zones_plugin.ZoneIndex()

        self._create_fixtures()

        self.mock_session = mock.Mock()
        self.mock_session.get_endpoint.return_value = \
            'http://localhost/glance/v2'
        patched_ses = mock.patch(
            'searchlight.elasticsearch.plugins.openstack_clients._get_session',
            return_value=self.mock_session)
        patched_ses.start()
        self.addCleanup(patched_ses.stop)

    def _create_fixtures(self):
        self.zone1 = _zone_fixture(ID1, TENANT1, name='test.com.',
                                   type='PRIMARY')
        self.zone2 = _zone_fixture(ID2, TENANT1, name='other.com.',
                                   type='PRIMARY')
        self.zone3 = _zone_fixture(ID3, TENANT2, name='tenant2.com.',
                                   type='PRIMARY')
        self.zones = (self.zone1, self.zone2, self.zone3)

    def test_missing_updated(self):
        """Designate records don't always have a value for 'updated'"""
        zone_to_test = dict(self.zone1)
        zone_to_test['updated_at'] = None
        serialized = self.plugin.serialize(zone_to_test)
        self.assertEqual(created_now, serialized['updated_at'])

    def test_facets(self):
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search/facets', is_admin=False
        )

        mock_engine = mock.Mock()
        self.plugin.engine = mock_engine

        mock_engine.search.return_value = {
            'aggregations': {
                'status': {
                    'buckets': [{'key': 'pending', 'doc_count': 2}]
                },
                'type': {
                    'buckets': [{'key': 'PRIMARY', 'doc_count': 2}]
                }
            }
        }

        facets = self.plugin.get_facets(fake_request.context)

        status_facet = list(filter(lambda f: f['name'] == 'status', facets))[0]
        expected_status = {
            'name': 'status',
            'options': [{'key': 'pending', 'doc_count': 2}],
            'type': 'string'
        }
        self.assertEqual(expected_status, status_facet)

        expected_agg_query = {
            'aggs': {
                'status': {'terms': {'field': 'status'}},
                'type': {'terms': {'field': 'type'}}
            },
            'query': {
                'filtered': {
                    'filter': {
                        'and': [
                            {'term': {'project_id': TENANT1}}
                        ]
                    }
                }
            }
        }
        mock_engine.search.assert_called_with(
            index=self.plugin.get_index_name(),
            doc_type=self.plugin.get_document_type(),
            body=expected_agg_query,
            ignore_unavailable=True,
            search_type='count'
        )
