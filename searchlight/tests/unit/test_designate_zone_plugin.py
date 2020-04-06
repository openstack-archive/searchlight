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

from searchlight.elasticsearch.plugins import designate
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight import pipeline
from searchlight.tests.unit.test_designate_recordset_plugin import \
    _recordset_fixture
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
        self.plugin = designate.zones.ZoneIndex()
        self.plugin.child_plugins = [designate.recordsets.RecordSetIndex()]

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

    def check_item(
            self, item, expected_type, event_type, payload, plugin_type):
        self.assertIsInstance(item, expected_type)
        self.assertEqual(event_type, item.event_type)
        self.assertIsInstance(item.plugin, plugin_type)
        self.assertEqual(payload, item.payload)

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
            },
            'hits': {'total': 2}
        }

        facets, _ = self.plugin.get_facets(fake_request.context)

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
        serialized = self.plugin.serialize(self.zone1)
        self.assertEqual(TENANT1, serialized['project_id'])

    def test_delete_zone(self):
        delete_event = (
            "dns.zone.delete",
            {
                "shard": 776,
                "minimum": 3600,
                "ttl": 3600,
                "serial": 1459409054,
                "deleted_at": None,
                "id": "3081593e-10ca-408c-af77-1397e689c177",
                "parent_zone_id": None,
                "retry": 600,
                "transferred_at": None,
                "version": 10,
                "type": "PRIMARY",
                "email": "foo@example.org",
                "status": "PENDING",
                "description": None,
                "deleted": "0",
                "updated_at": "2016-03-31T17:39:05.000000",
                "expire": 86400,
                "masters": [],
                "name": "myzone.net.",
                "tenant_id": "80264096ac454d3d904002491fafe2ec",
                "created_at": "2016-03-31T05:30:02.000000",
                "pool_id": "794ccc2c-d751-44fe-b57f-8894c9f5c842",
                "refresh": 3588,
                "delayed_notify": False,
                "action": "DELETE",
                "attributes": []
            },
            "2016-03-31 17:39:05.495730"
        )

        handler = self.plugin.get_notification_handler()
        event_handlers = handler.get_event_handlers()

        with mock.patch.object(self.plugin.index_helper,
                               'delete_document') as mock_zone_delete:
            with mock.patch.object(
                    self.plugin.child_plugins[0].index_helper,
                    'delete_documents') as mock_recordset_delete:
                with mock.patch(
                        'elasticsearch.helpers.scan') as mock_scan:
                    # mock scan method to return child recordset
                    mock_scan.return_value = [{'_id': 'recordset1'}]
                    type_handler = event_handlers.get(delete_event[0], None)
                    result = type_handler(*delete_event)
                    self.assertEqual(1, mock_zone_delete.call_count)
                    self.assertEqual(1, mock_recordset_delete.call_count)
                    self.assertEqual(2, len(result))
                    self.check_item(result[0],
                                    pipeline.DeleteItem,
                                    delete_event[0],
                                    delete_event[1],
                                    designate.recordsets.RecordSetIndex
                                    )
                    self.assertEqual("recordset1", result[0].doc_id)
                    self.check_item(result[1],
                                    pipeline.DeleteItem,
                                    delete_event[0],
                                    delete_event[1],
                                    designate.zones.ZoneIndex)
                    self.assertEqual(
                        "3081593e-10ca-408c-af77-1397e689c177",
                        result[1].doc_id)

    def test_update_zone(self):
        update_event = (
            "dns.zone.update",
            {
                "shard": 776,
                "minimum": 3600,
                "ttl": 4800,
                "serial": 1459402269,
                "deleted_at": None,
                "id": "3081593e-10ca-408c-af77-1397e689c177",
                "parent_zone_id": None,
                "retry": 600,
                "transferred_at": None,
                "version": 2,
                "type": "PRIMARY",
                "email": "foo@example.org",
                "status": "PENDING",
                "description": None,
                "deleted": "0",
                "updated_at": "2016-03-31T05:31:10.000000",
                "expire": 86400,
                "masters": [],
                "name": "myzone.net.",
                "tenant_id": "80264096ac454d3d904002491fafe2ec",
                "created_at": "2016-03-31T05:30:02.000000",
                "pool_id": "794ccc2c-d751-44fe-b57f-8894c9f5c842",
                "refresh": 3588,
                "delayed_notify": False,
                "action": "UPDATE",
                "attributes": []
            },
            "2016-03-31 05:31:10.232924"
        )

        handler = self.plugin.get_notification_handler()
        event_handlers = handler.get_event_handlers()

        with mock.patch.object(self.plugin.index_helper,
                               'save_document') as mock_save:
            result = event_handlers.get(update_event[0])(*update_event)
            self.assertEqual(1, mock_save.call_count)
            self.check_item(result,
                            pipeline.IndexItem,
                            update_event[0],
                            update_event[1],
                            designate.zones.ZoneIndex
                            )

    def test_initial_create_zone(self):
        create_event = (
            "dns.zone.create",
            {
                "shard": 776,
                "minimum": 3600,
                "ttl": 3600,
                "serial": 1459402202,
                "deleted_at": None,
                "id": "3081593e-10ca-408c-af77-1397e689c177",
                "parent_zone_id": None,
                "retry": 600,
                "transferred_at": None,
                "version": 1,
                "type": "PRIMARY",
                "email": "foo@example.org",
                "status": "PENDING",
                "description": None,
                "deleted": "0",
                "updated_at": None,
                "expire": 86400,
                "masters": [],
                "name": "myzone.net.",
                "tenant_id": "80264096ac454d3d904002491fafe2ec",
                "created_at": "2016-03-31T05:30:02.000000",
                "pool_id": "794ccc2c-d751-44fe-b57f-8894c9f5c842",
                "refresh": 3588,
                "delayed_notify": False,
                "action": "CREATE",
                "attributes": []
            },
            "2016-03-31 05:30:02.692222"
        )
        handler = self.plugin.get_notification_handler()
        with mock.patch(
                'searchlight.elasticsearch.plugins.designate._get_recordsets'
        ) as mock_list:
            with mock.patch.object(handler.index_helper,
                                   'save_documents') as mock_save:
                with mock.patch.object(handler.recordset_helper,
                                       'save_documents') as mock_rs_save:
                    mock_list.return_value = [
                        _recordset_fixture(
                            "1",
                            "3081593e-10ca-408c-af77-1397e689c177",
                            "80264096ac454d3d904002491fafe2ec",
                            name='www.test.com.',
                            type='A',
                            records=['192.0.2.1'])
                    ]
                    result = handler.process({},
                                             "central.ubunt",
                                             create_event[0],
                                             create_event[1],
                                             {'timestamp': create_event[2]}
                                             )
                    self.assertEqual(1, mock_save.call_count)
                    self.assertEqual(1, mock_rs_save.call_count)
                    self.assertEqual(len(result), 2)
                    self.check_item(result[0],
                                    pipeline.IndexItem,
                                    create_event[0],
                                    create_event[1],
                                    designate.zones.ZoneIndex)
                    self.assertEqual("3081593e-10ca-408c-af77-1397e689c177",
                                     result[0].doc_id)
                    self.check_item(result[1],
                                    pipeline.IndexItem,
                                    create_event[0],
                                    create_event[1],
                                    designate.recordsets.RecordSetIndex)
                    self.assertEqual("1", result[1].doc_id)
