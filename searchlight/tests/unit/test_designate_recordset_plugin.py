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
from unittest import mock

from searchlight.elasticsearch.plugins.designate import \
    recordsets as recordsets_plugin
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight import pipeline
from searchlight.tests.unit import utils as unit_test_utils
import searchlight.tests.utils as test_utils


now = datetime.datetime.utcnow()
five_mins = datetime.timedelta(minutes=5)
updated_now = now.strftime('%Y-%m-%dT%H:%M:%SZ')
created_now = (now - five_mins).strftime('%Y-%m-%dT%H:%M:%SZ')

USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'

TENANT1 = u'4d64ac83-87af-4d2a-b884-cc42c3e8f2c0'
TENANT2 = u'c6993374-7c4b-4f18-b317-85e3acdfd259'

# Zone ids
ZONE_ID1 = u'9b4c2de5-dead-0000-beef-e3b99695aa69'
ZONE_ID2 = u'0c3dae67-c4d3-42d6-9d8d-98da56321bca'

ID1 = u'4d6c2de5-c4d3-0000-4e4e-acd99695a222'
ID2 = u'98543543-3443-acdf-deac-3423423cdadf'
ID3 = u'90754354-bc43-234b-12b5-789234bcdefa'


def _recordset_fixture(id, zone_id, tenant_id, name, **kwargs):
    recordset = {
        'tenant_id': tenant_id,
        'zone_id': zone_id,
        'name': name,
        'ttl': 3600,
        'status': 'pending',
        'created_at': created_now,
        'updated_at': updated_now,
        "id": id
    }
    recordset.update(**kwargs)
    return recordset


class TestRecordsetPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestRecordsetPlugin, self).setUp()
        self.plugin = recordsets_plugin.RecordSetIndex()

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
        self.recordset1 = _recordset_fixture(
            ID1, ZONE_ID1, TENANT1, name='www.test.com.', type='A',
            records=['192.0.2.1'])
        self.recordset2 = _recordset_fixture(
            ID1, ZONE_ID1, TENANT1, name='www2.test.com.', type='A',
            records=['192.0.5.1', '192.0.1.1'])
        self.recordset3 = _recordset_fixture(
            ID1, ZONE_ID2, TENANT1, name='www.other.com.', type='A',
            records=['192.0.128.128'])

        self.recordsets = (self.recordset1, self.recordset2, self.recordset3)

    def test_missing_updated(self):
        """Designate records don't always have a value for 'updated'"""
        set_to_test = dict(self.recordset1)
        set_to_test['updated_at'] = None
        serialized = self.plugin.serialize(set_to_test)
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
                    'buckets': [{'key': 'A', 'doc_count': 2}]
                }
            },
            'hits': {'total': 2}
        }

        facets, _ = self.plugin.get_facets(fake_request.context)

        zone_id_facet = list(filter(lambda f: f['name'] == 'zone_id',
                                    facets))[0]
        expected_zone_id = {
            'name': 'zone_id',
            'type': 'string',
            'resource_type': self.plugin.parent_plugin_type(),
            'parent': True
        }

        self.assertEqual(expected_zone_id, zone_id_facet)

        status_facet = list(filter(lambda f: f['name'] == 'status', facets))[0]
        expected_status = {
            'name': 'status',
            'options': [{'key': 'pending', 'doc_count': 2}],
            'type': 'string'
        }
        self.assertEqual(expected_status, status_facet)

        expected_agg_query = {
            'aggs': dict(unit_test_utils.simple_facet_field_agg(name)
                         for name in ('status', 'type')),
            'query': {
                'bool': {
                    'filter': {
                        'bool': {
                            'must': {'term': {ROLE_USER_FIELD: 'user'}},
                            'should': [{'term': {'project_id': TENANT1}}],
                            'minimum_should_match': 1
                        }
                    }
                }
            }
        }
        mock_engine.search.assert_called_with(
            index=self.plugin.alias_name_search,
            doc_type=self.plugin.get_document_type(),
            body=expected_agg_query,
            ignore_unavailable=True,
            size=0
        )

    def test_serialize(self):
        serialized = self.plugin.serialize(self.recordset1)
        self.assertEqual(TENANT1, serialized['project_id'])

    def test_create_recordset(self):
        """Test recordset create event"""
        mock_engine = mock.Mock()
        self.plugin.engine = mock_engine

        create_event = (
            'dns.recordset.create',
            {
                "zone_id": "3081593e-10ca-408c-af77-1397e689c177",
                "tenant_id": "80264096ac454d3d904002491fafe2ec",
                "created_at": "2016-03-31T05:48:53.000000",
                "description": None,
                "updated_at": None,
                "records": [{
                    "status": "PENDING",
                    "zone_id": "3081593e-10ca-408c-af77-1397e689c177",
                    "managed": False,
                    "managed_resource_id": None,
                    "managed_resource_type": None,
                    "tenant_id": "80264096ac454d3d904002491fafe2ec",
                    "created_at": "2016-03-31T05:48:54.000000",
                    "managed_extra": None,
                    "updated_at": None,
                    "managed_plugin_type": None,
                    "version": 1,
                    "managed_plugin_name": None,
                    "managed_tenant_id": None,
                    "action": "CREATE",
                    "hash": "8402992213c4c985429e9f2b23a18847",
                    "managed_resource_region": None,
                    "recordset_id": "cfe39618-49da-4877-914b-f25ef0fb3dc1",
                    "data": "10.0.0.1",
                    "id": "01835dc4-b805-4c8f-b962-2a96880f40c7",
                    "serial": 1459403333,
                    "description": None
                }],
                "version": 1,
                "ttl": None,
                "type": "A",
                "id": "cfe39618-49da-4877-914b-f25ef0fb3dc1",
                "name": "www.myzone.net."
            },
            '2016-03-31 05:48:54.102791'
        )
        handler = self.plugin.get_notification_handler()
        event_handlers = handler.get_event_handlers()

        with mock.patch.object(self.plugin.index_helper,
                               'save_document') as mock_save:
            type_handler = event_handlers.get(create_event[0], None)
            result = type_handler(*create_event)
            self.assertEqual(1, mock_save.call_count)
            self.assertIsInstance(result, pipeline.IndexItem)
            self.assertIsInstance(result.plugin,
                                  recordsets_plugin.RecordSetIndex)
            self.assertEqual(create_event[0], result.event_type)

    def test_delete_recordset(self):
        """Test recordset delete event"""
        mock_engine = mock.Mock()
        self.plugin.engine = mock_engine

        delete_event = (
            "dns.recordset.delete",
            {
                "zone_id": "3081593e-10ca-408c-af77-1397e689c177",
                "tenant_id": "80264096ac454d3d904002491fafe2ec",
                "created_at": "2016-03-31T05:48:53.000000",
                "description": None,
                "updated_at": "2016-03-31T07:24:14.000000",
                "records": [{
                    "status": "PENDING",
                    "zone_id": "3081593e-10ca-408c-af77-1397e689c177",
                    "managed": False,
                    "managed_resource_id": None,
                    "managed_resource_type": None,
                    "tenant_id": "80264096ac454d3d904002491fafe2ec",
                    "created_at": "2016-03-31T05:48:54.000000",
                    "managed_extra": None,
                    "updated_at": "2016-03-31T07:24:14.000000",
                    "managed_plugin_type": None,
                    "version": 3,
                    "managed_plugin_name": None,
                    "managed_tenant_id": None,
                    "action": "DELETE",
                    "hash": "8402992213c4c985429e9f2b23a18847",
                    "managed_resource_region": None,
                    "recordset_id": "cfe39618-49da-4877-914b-f25ef0fb3dc1",
                    "data": "10.0.0.1",
                    "id": "01835dc4-b805-4c8f-b962-2a96880f40c7",
                    "serial": 1459409054,
                    "description": None
                }],
                "version": 3,
                "ttl": None,
                "type": "A",
                "id": "cfe39618-49da-4877-914b-f25ef0fb3dc1",
                "name": "www.myzone.net."
            },
            "2016-03-31 07:24:14.945626"
        )

        handler = self.plugin.get_notification_handler()
        event_handlers = handler.get_event_handlers()

        with mock.patch.object(self.plugin.index_helper,
                               'delete_document') as mock_delete:
            type_handler = event_handlers.get(delete_event[0], None)
            result = type_handler(*delete_event)
            self.assertEqual(1, mock_delete.call_count)
            self.assertIsInstance(result, pipeline.DeleteItem)
            self.assertIsInstance(result.plugin,
                                  recordsets_plugin.RecordSetIndex)
            self.assertEqual(delete_event[0], result.event_type)
            self.assertEqual(delete_event[1]["id"], result.doc_id)
