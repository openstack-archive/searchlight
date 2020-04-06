# Copyright (c) 2015-2016 Hewlett-Packard Development Company, L.P.
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
from unittest import mock

from oslo_serialization import jsonutils
from oslo_utils import uuidutils

from searchlight.listener import NotificationEndpoint
from searchlight.pipeline import PipelineManager
from searchlight.tests import functional
from searchlight.tests.functional import generate_load_data
from searchlight.tests.functional import mock_glance_pyclient
from searchlight.tests.functional import test_api
from searchlight.tests.functional import test_listener
from searchlight.tests import utils


member_list = 'glanceclient.v2.image_members.Controller.list'


class TestGlancePlugins(functional.FunctionalTest):
    def setUp(self):
        super(TestGlancePlugins, self).setUp()
        self.images_plugin = self.initialized_plugins['OS::Glance::Image']
        self.metadefs_plugin = self.initialized_plugins['OS::Glance::Metadef']

    def test_image_property_protection(self):
        doc_with_properties = {
            "owner": test_api.TENANT1,
            "id": uuidutils.generate_uuid(),
            "name": "doc with properties",
            "x_none_permitted": "nobody can do anything",
            "x_foo_matcher": "admin only",
            "x_owner_anything": "member or admin",
            "x_none_read": "nobody can read",
            "any_old_property": "restricted to admins",
            "x_foo_anybody": "anybody may read",
            "spl_read_only_prop": "spl_role only",
            "visibility": "public",
            "created_at": "2016-04-06T12:48:18Z"
        }
        self._index(self.images_plugin,
                    [doc_with_properties])

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT1)
        self.assertEqual(200, response.status_code)
        # Image_type is metadata on image and not a 'core' glance property.
        # Property protection policy defines access similar to other metadata
        # here.
        # We need to remove 'image_type' since non-core properties are
        # allowed only for admin role defined in test policy file located at
        # searchlight/tests/etc/property-protections.conf (See last section)
        expect_removed = ["x_none_permitted", "x_foo_matcher", "x_none_read",
                          "any_old_property", "spl_read_only_prop",
                          'image_type']
        expected_result = dict((k, v)
                               for k, v in doc_with_properties.items()
                               if k not in expect_removed)
        expected_result['members'] = []
        expected_result['project_id'] = test_api.TENANT1
        self.assertEqual([expected_result], self._get_hit_source(json_content))

        # Test with the 'spl_role' role
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT1,
                                                      role="spl_role")
        self.assertEqual(200, response.status_code)
        expect_removed = ["x_none_permitted", "x_foo_matcher", "x_none_read",
                          "any_old_property", "x_owner_anything",
                          "image_type"]
        expected_result = dict((k, v)
                               for k, v in doc_with_properties.items()
                               if k not in expect_removed)
        expected_result['members'] = []
        expected_result['project_id'] = test_api.TENANT1

        self.assertEqual([expected_result], self._get_hit_source(json_content))

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT1,
                                                      role="admin")
        self.assertEqual(200, response.status_code)
        expect_removed = ["x_none_permitted", "x_none_read"]
        expected_result = dict((k, v)
                               for k, v in doc_with_properties.items()
                               if k not in expect_removed)
        expected_result['members'] = []
        expected_result['project_id'] = test_api.TENANT1
        expected_result['image_type'] = 'image'

        self.assertEqual([expected_result], self._get_hit_source(json_content))

    def test_rbac_admin(self):
        """Test that an admin has access to everything"""
        image_doc = {
            "owner": test_api.TENANT1,
            "id": uuidutils.generate_uuid(),
            "name": "abc",
            "visibility": "private",
            "members": [],
            "created_at": "2016-04-06T12:48:18Z"
        }
        metadef_doc = {
            "owner": test_api.TENANT2,
            "visibility": "private",
            "namespace": "some.value1",
            "objects": [],
            "tags": [],
            "properties": {},
            "created_at": "2016-04-06T12:48:18Z"
        }

        fake_member = {"member_id": test_api.TENANT1, "status": "accepted"}
        with mock.patch(member_list, return_value=[fake_member]):
            self._index(self.images_plugin, [image_doc])

        self._index(self.metadefs_plugin, [metadef_doc])

        # Expected output format is a bit different
        metadef_doc.update({
            'properties': [],
            'protected': None,
            'resource_types': [],
            'name': metadef_doc['namespace'],
            'id': metadef_doc['namespace'],
            'description': None,
            'display_name': None,
            'updated_at': None,
            'project_id': test_api.TENANT2
        })
        image_doc['project_id'] = test_api.TENANT1

        # An ordinary user in TENANT3 shouldn"t have any access
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT3)
        self.assertEqual([], self._get_hit_source(json_content))

        # An admin without specifying all_projects should get the same
        # result as an ordinary user
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT3,
                                                      role='admin')
        self.assertEqual([], self._get_hit_source(json_content))

        # An admin should have access to all (at least in KS v2)
        admin_match_all = {
            'all_projects': True
        }
        admin_match_all.update(test_api.MATCH_ALL)
        response, json_content = self._search_request(admin_match_all,
                                                      test_api.TENANT3,
                                                      role='admin')
        image_doc['image_type'] = 'image'
        self.assertEqual([image_doc, metadef_doc],
                         self._get_hit_source(json_content))

    def test_image_rbac_owner(self):
        """Test glance.image RBAC based on the "owner" field"""
        id_1 = uuidutils.generate_uuid()
        tenant1_doc = {
            "owner": test_api.TENANT1,
            "id": id_1,
            "visibility": "private",
            "name": "owned by tenant 1",
            "created_at": "2016-04-06T12:48:18Z"
        }
        tenant2_doc = {
            "owner": test_api.TENANT2,
            "id": uuidutils.generate_uuid(),
            "visibility": "private",
            "name": "owned by tenant 2",
            "created_at": "2016-04-06T12:48:18Z"
        }

        with mock.patch(member_list, return_value=[]):
            self._index(self.images_plugin,
                        [tenant1_doc, tenant2_doc])

        tenant1_doc["members"] = []
        tenant2_doc["members"] = []
        tenant1_doc["project_id"] = tenant1_doc["owner"]
        tenant2_doc["project_id"] = tenant2_doc["owner"]

        # Query for everything as one tenant then the other
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT1)
        self.assertEqual(200, response.status_code)
        self.assertEqual([tenant1_doc], self._get_hit_source(json_content))

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT2)
        self.assertEqual(200, response.status_code)
        self.assertEqual([tenant2_doc], self._get_hit_source(json_content))

        # Query the hidden doc explicitly
        query = {
            "query": {
                "match": {"id": id_1}
            }
        }
        response, json_content = self._search_request(query,
                                                      test_api.TENANT2)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_image_rbac_member(self):
        """Test glance.image RBAC based on the "member" field"""
        owner = uuidutils.generate_uuid()
        accessible_doc = {
            "owner": owner,
            "id": uuidutils.generate_uuid(),
            "visibility": "shared",
            "name": "accessible doc",
            "created_at": "2016-04-06T12:48:18Z"
        }
        inaccessible_doc = {
            "owner": uuidutils.generate_uuid(),
            "id": uuidutils.generate_uuid(),
            "visibility": "shared",
            "name": "inaccessible_doc doc",
            "created_at": "2016-04-06T12:48:18Z"
        }

        # Assign TENANT1, TENANT2 to accessible doc and a fake member to
        # inaccessible doc
        made_up_tenant = uuidutils.generate_uuid()
        fake_members = (
            [{"member_id": test_api.TENANT1, "status": "accepted"},
             {"member_id": test_api.TENANT2, "status": "accepted"}],
            [{"member_id": made_up_tenant, "status": "accepted"}]
        )
        with mock.patch(member_list, side_effect=fake_members):
            self._index(self.images_plugin,
                        [accessible_doc, inaccessible_doc])

        accessible_doc["project_id"] = accessible_doc["owner"]
        inaccessible_doc["members"] = [made_up_tenant]

        # Someone in TENANT1 or TENANT2 should have access to "accessible_doc"
        # but should only see their tenant in 'members'
        accessible_doc["members"] = [test_api.TENANT1]
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT1)
        self.assertEqual(200, response.status_code)
        self.assertEqual([accessible_doc], self._get_hit_source(json_content))

        accessible_doc["members"] = [test_api.TENANT2]
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT2)
        self.assertEqual(200, response.status_code)
        self.assertEqual([accessible_doc], self._get_hit_source(json_content))

        # A user in 'owner' should see the member list
        accessible_doc["members"] = [test_api.TENANT1, test_api.TENANT2]
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      owner)
        self.assertEqual(200, response.status_code)
        self.assertEqual([accessible_doc], self._get_hit_source(json_content))

        # An admin should see the member list even if they're in another tenant
        accessible_doc["members"] = [test_api.TENANT1, test_api.TENANT2]
        accessible_doc["image_type"] = "image"
        response, json_content = self._search_request(
            {"query": {"term": {"owner": owner}}, "all_projects": True},
            uuidutils.generate_uuid(),
            role="admin")
        self.assertEqual(200, response.status_code)
        self.assertEqual([accessible_doc], self._get_hit_source(json_content))

        # A user in another tenant shouldn't see it at all
        response, json_content = self._search_request(
            test_api.MATCH_ALL, uuidutils.generate_uuid())
        self.assertEqual(200, response.status_code)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_image_rbac_visibility(self):
        """Test that "visibility: public" makes images visible"""
        visible_doc = {
            "owner": uuidutils.generate_uuid(),
            "id": uuidutils.generate_uuid(),
            "visibility": "public",
            "name": "visible doc",
            "created_at": "2016-04-06T12:48:18Z"
        }
        invisible_doc = {
            "owner": uuidutils.generate_uuid(),
            "id": uuidutils.generate_uuid(),
            "visibility": "private",
            "name": "visible doc",
            "created_at": "2016-04-06T12:48:18Z"
        }

        # Generate a fake tenant id for invisible_doc's "members"
        fake_member = {"member_id": uuidutils.generate_uuid(),
                       "status": "accepted"}
        with mock.patch(member_list, return_value=[fake_member]):
            self._index(self.images_plugin,
                        [visible_doc, invisible_doc],
                        test_api.TENANT1)

        visible_doc["members"] = []
        visible_doc["project_id"] = visible_doc["owner"]

        # visible doc should be visible to any user
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT2)
        self.assertEqual(200, response.status_code)
        self.assertEqual([visible_doc], self._get_hit_source(json_content))

    def test_metadef_rbac_visibility(self):
        visible_doc = {
            "owner": uuidutils.generate_uuid(),
            "id": uuidutils.generate_uuid(),
            "visibility": "public",
            "name": "visible doc",
            "namespace": "TEST_VISIBLE",
            "properties": {},
            "tags": [],
            "objects": [],
            "created_at": "2016-04-06T12:48:18Z"
        }
        invisible_doc = {
            "owner": uuidutils.generate_uuid(),
            "id": uuidutils.generate_uuid(),
            "visibility": "private",
            "name": "visible doc",
            "namespace": "TEST_INVISIBLE",
            "properties": {},
            "tags": [],
            "objects": [],
            "created_at": "2016-04-06T12:48:18Z"
        }
        self._index(self.metadefs_plugin,
                    [visible_doc, invisible_doc])

        visible_doc["id"] = visible_doc["namespace"]
        visible_doc["name"] = visible_doc["namespace"]
        visible_doc["project_id"] = visible_doc["owner"]
        visible_doc.update({
            "resource_types": [],
            "properties": [],
            "description": None,
            "display_name": None,
            "protected": None,
            "updated_at": None
        })

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT2)
        self.assertEqual(200, response.status_code)
        self.assertEqual([visible_doc], self._get_hit_source(json_content))

    def test_metadef_rbac_owner(self):
        visible_doc = {
            "owner": test_api.TENANT1,
            "namespace": "VISIBLE",
            "visibility": "private",
            "properties": {},
            "tags": [],
            "objects": [],
            "created_at": "2016-04-06T12:48:18Z"
        }
        invisible_doc = {
            "owner": uuidutils.generate_uuid(),
            "namespace": "INVISIBLE",
            "visibility": "private",
            "properties": {},
            "tags": [],
            "objects": [],
            "created_at": "2016-04-06T12:48:18Z"
        }
        self._index(self.metadefs_plugin,
                    [visible_doc, invisible_doc])

        visible_doc["id"] = visible_doc["namespace"]
        visible_doc["name"] = visible_doc["namespace"]
        visible_doc["project_id"] = visible_doc["owner"]
        visible_doc.update({
            "resource_types": [],
            "properties": [],
            "description": None,
            "display_name": None,
            "protected": None,
            "updated_at": None
        })

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT1)
        self.assertEqual(200, response.status_code)
        self.assertEqual([visible_doc], self._get_hit_source(json_content))

        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT2)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_index_with_dot_in_field(self):
        test_doc = {
            "owner": test_api.TENANT1,
            "id": uuidutils.generate_uuid(),
            "name": "test image",
            "visibility": "public",
            "property_1.2.3": "test_property",
            "created_at": "2016-04-06T12:48:18Z"
        }

        self._index(self.images_plugin, [test_doc])
        response, json_content = self._search_request(test_api.MATCH_ALL,
                                                      test_api.TENANT1,
                                                      role="admin")
        self.assertEqual(200, response.status_code)
        expected = test_doc.copy()
        expected.update(image_type="image", members=[],
                        project_id=test_api.TENANT1)
        self.assertEqual([expected], self._get_hit_source(json_content))


class TestGlanceListener(test_listener.TestSearchListenerBase):
    def __init__(self, *args, **kwargs):
        super(TestGlanceListener, self).__init__(*args, **kwargs)

        self.image_events = self._load_fixture_data('events/images.json')
        self.metadef_events = self._load_fixture_data('events/metadefs.json')

    def setUp(self):
        super(TestGlanceListener, self).setUp()
        openstack_client_mod = "searchlight.elasticsearch.plugins." \
                               "openstack_clients.get_glanceclient"
        osclient_patcher = mock.patch(
            openstack_client_mod, mock_glance_pyclient.get_fake_glance_client
        )
        osclient_patcher.start()
        self.addCleanup(osclient_patcher.stop)

        self.images_plugin = self.initialized_plugins['OS::Glance::Image']
        self.metadefs_plugin = self.initialized_plugins['OS::Glance::Metadef']

        notification_plugins = {
            plugin.document_type: utils.StevedoreMock(plugin)
            for plugin in (self.images_plugin, self.metadefs_plugin)}
        self.notification_endpoint = NotificationEndpoint(
            notification_plugins,
            PipelineManager(notification_plugins)
        )

        self.images_index = self.images_plugin.alias_name_listener
        self.metadefs_index = self.metadefs_plugin.alias_name_listener

    def test_image_create_event(self):
        """Send image.create notification event to listener"""
        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event, self.images_index)
        result = self._verify_event_processing(create_event)
        verification_keys = ['id', 'status']
        self._verify_result(create_event, verification_keys, result)

    def test_image_update_conflict(self):
        """Send an outdated image.update notification event to listener,
           test if the document will be updated
        """
        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event, self.images_index)

        update_event = self.image_events["image.update"]
        self._send_event_to_listener(update_event, self.images_index)

        outdate_update_event = copy.deepcopy(update_event)
        outdate_update_event['payload']['updated_at'] = ("2015-09-01T"
                                                         "09:06:18.000000")
        self._send_event_to_listener(outdate_update_event, self.images_index)
        result = self._verify_event_processing(update_event)

        # Check if outdated update notification failed
        verification_keys = ['updated_at']
        self._verify_result(update_event, verification_keys, result)

    def test_image_update_event(self):
        """Send image.update notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event, self.images_index)

        update_event = self.image_events["image.update"]
        self._send_event_to_listener(update_event, self.images_index)
        result = self._verify_event_processing(update_event)
        verification_keys = ['name', 'protected']
        self._verify_result(update_event, verification_keys, result)

    def test_image_delete_event(self):
        """Send image.delete notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event, self.images_index)
        self._verify_event_processing(create_event)

        delete_event = self.image_events["image.delete"]
        self._send_event_to_listener(delete_event, self.images_index)
        self._verify_event_processing(delete_event, 0)

    def test_image_member_create_event(self):
        """Send member.create notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event, self.images_index)

        create_event = self.image_events["image.member.create"]
        self._send_event_to_listener(create_event, self.images_index)
        result = self._verify_event_processing(create_event,
                                               owner=test_listener.OWNER1)

        # member.create event will have status of "pending" which should not
        # add the member to the image.members list
        self.assertEqual(0,
                         len(result['hits']['hits'][0]['_source']['members']))

    def test_image_member_update_event(self):
        """Send member.update notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event, self.images_index)

        update_event = self.image_events["image.member.update"]
        self._send_event_to_listener(update_event, self.images_index)
        result = self._verify_event_processing(update_event,
                                               owner=test_listener.OWNER1)

        # member.update event with the status of "accepted" which should
        # add the member to the image.members list
        self.assertEqual(1,
                         len(result['hits']['hits'][0]['_source']['members']))

    def test_image_member_delete_event(self):
        """Send member.delete notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event, self.images_index)

        update_event = self.image_events["image.member.update"]
        self._send_event_to_listener(update_event, self.images_index)
        result = self._verify_event_processing(update_event,
                                               owner=test_listener.OWNER1)
        self.assertEqual(1,
                         len(result['hits']['hits'][0]['_source']['members']))

        delete_event = self.image_events["image.member.delete"]
        self._send_event_to_listener(delete_event, self.images_index)
        result = self._verify_event_processing(delete_event,
                                               owner=test_listener.OWNER1)

        # member.delete event should remove the member
        self.assertEqual(0,
                         len(result['hits']['hits'][0]['_source']['members']))

    def test_md_namespace_create_event(self):
        """Send metadef_namespace.create notification event to listener"""
        create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(create_event, self.metadefs_index)
        result = self._verify_event_processing(create_event)
        verification_keys = ['namespace', 'display_name']
        self._verify_result(create_event, verification_keys, result)

    def test_md_namespace_update_event(self):
        """Send metadef_namespace.update notification event to listener"""

        create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(create_event, self.metadefs_index)

        update_event = self.metadef_events["metadef_namespace.update"]
        self._send_event_to_listener(update_event, self.metadefs_index)
        result = self._verify_event_processing(update_event)
        verification_keys = ['display_name', 'description', 'namespace',
                             'created_at', 'updated_at', 'owner', 'visibility',
                             'protected']
        self._verify_result(update_event, verification_keys, result)

    def test_md_namespace_update_conflict(self):
        """Send an outdated metadef_namespace.update notification event to
        listener, test if the document will be updated
        """
        create_event = self.metadef_events['metadef_namespace.create']
        self._send_event_to_listener(create_event, self.metadefs_index)
        update_event = self.metadef_events['metadef_namespace.update']
        self._send_event_to_listener(update_event, self.metadefs_index)

        outdate_update_event = copy.deepcopy(update_event)
        outdate_update_event['payload']['updated_at'] = '2015-09-01T03:51:54Z'
        self._send_event_to_listener(outdate_update_event, self.metadefs_index)
        result = self._verify_event_processing(outdate_update_event)

        # check if outdated update event failed
        verification_keys = ['updated_at']
        self._verify_result(update_event, verification_keys, result)

    def test_md_namespace_delete_event(self):
        """Send metadef_namespace.delete notification event to listener"""

        create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(create_event, self.metadefs_index)
        self._verify_event_processing(create_event)

        delete_event = self.metadef_events["metadef_namespace.delete"]
        self._send_event_to_listener(delete_event, self.metadefs_index)
        self._verify_event_processing(delete_event, 0)

    def test_md_object_create_event(self):
        """Send metadef_object.create notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        obj_create_event = self.metadef_events["metadef_object.create"]
        self._send_event_to_listener(obj_create_event, self.metadefs_index)
        result = self._verify_event_processing(
            obj_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['objects']
        self.assertEqual(1, len(result))
        self.assertEqual(obj_create_event['payload']['name'],
                         result[0]['name'])

    def test_md_object_update_event(self):
        """Send metadef_object.update notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        obj_create_event = self.metadef_events["metadef_object.create"]
        self._send_event_to_listener(obj_create_event, self.metadefs_index)

        obj_update_event = self.metadef_events["metadef_object.update"]
        self._send_event_to_listener(obj_update_event, self.metadefs_index)
        result = self._verify_event_processing(
            obj_update_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['objects'][0]
        self.assertEqual(2, len(result['properties']))

    def test_md_object_delete_event(self):
        """Send metadef_object.delete notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        obj_create_event = self.metadef_events["metadef_object.create"]
        self._send_event_to_listener(obj_create_event, self.metadefs_index)
        result = self._verify_event_processing(
            obj_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['objects']
        self.assertEqual(1, len(result))

        obj_delete_event = self.metadef_events["metadef_object.delete"]
        self._send_event_to_listener(obj_delete_event, self.metadefs_index)
        result = self._verify_event_processing(
            obj_delete_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['objects']
        self.assertEqual(0, len(result))

    def test_md_property_create_event(self):
        """Send metadef_property.create notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        prop_create_event = self.metadef_events["metadef_property.create"]
        self._send_event_to_listener(prop_create_event, self.metadefs_index)
        result = self._verify_event_processing(
            prop_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['properties']
        self.assertEqual(1, len(result))
        self.assertEqual(prop_create_event['payload']['type'],
                         result[0]['type'])

    def test_md_property_update_event(self):
        """Send metadef_property.update notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        prop_update_event = self.metadef_events["metadef_property.update"]
        self._send_event_to_listener(prop_update_event, self.metadefs_index)
        result = self._verify_event_processing(
            prop_update_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['properties']
        self.assertEqual(1, len(result))
        self.assertEqual(prop_update_event['payload']['maximum'],
                         result[0]['maximum'])

    def test_md_property_delete_event(self):
        """Send metadef_object.delete notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        prop_create_event = self.metadef_events["metadef_property.create"]
        self._send_event_to_listener(prop_create_event, self.metadefs_index)
        result = self._verify_event_processing(
            prop_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['properties']
        self.assertEqual(1, len(result))

        prop_delete_event = self.metadef_events["metadef_property.delete"]
        self._send_event_to_listener(prop_delete_event, self.metadefs_index)
        result = self._verify_event_processing(
            prop_delete_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['properties']
        self.assertEqual(0, len(result))

    def test_md_resource_type_create_event(self):
        """Send metadef_property.create notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        res_type_create_event = \
            self.metadef_events["metadef_resource_type.create"]
        self._send_event_to_listener(res_type_create_event,
                                     self.metadefs_index)
        result = self._verify_event_processing(
            res_type_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['resource_types']
        self.assertEqual(1, len(result))
        self.assertEqual(res_type_create_event['payload']['name'],
                         result[0]['name'])

    def test_md_resource_type_delete_event(self):
        """Send metadef_property.create notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event, self.metadefs_index)

        res_type_create_event = \
            self.metadef_events["metadef_resource_type.create"]
        self._send_event_to_listener(res_type_create_event,
                                     self.metadefs_index)
        result = self._verify_event_processing(
            res_type_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['resource_types']
        self.assertEqual(1, len(result))

        rs_type_delete_event = \
            self.metadef_events["metadef_resource_type.delete"]
        self._send_event_to_listener(rs_type_delete_event, self.metadefs_index)
        result = self._verify_event_processing(
            rs_type_delete_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['resource_types']
        self.assertEqual(0, len(result))


class TestGlanceLoad(functional.FunctionalTest):

    def setUp(self):
        super(TestGlanceLoad, self).setUp()

        openstack_client_mod = "searchlight.elasticsearch.plugins." \
                               "openstack_clients.get_glanceclient"
        osclient_patcher = mock.patch(
            openstack_client_mod, mock_glance_pyclient.get_fake_glance_client
        )
        osclient_patcher.start()
        self.addCleanup(osclient_patcher.stop)

        self.images_count, self.images_owner = \
            self._get_glance_image_owner_and_count()
        self.metadefs_count, self.metadefs_owner = \
            self._get_glance_metadefs_owner_and_count()
        self.all_doc_count = self.images_count + self.metadefs_count

        self.images_plugin = self.initialized_plugins['OS::Glance::Image']
        self.metadefs_plugin = self.initialized_plugins['OS::Glance::Metadef']

    def _get_glance_image_owner_and_count(self):
        with open(generate_load_data.IMAGES_FILE, "r+b") as file:
            images_data = jsonutils.load(file)
        if len(images_data) > 0:
            return len(images_data), images_data[0]['owner']

    def _get_glance_metadefs_owner_and_count(self):
        with open(generate_load_data.METADEFS_FILE, "r+b") as file:
            metadefs_data = jsonutils.load(file)
        if len(metadefs_data) > 0:
            return len(metadefs_data), metadefs_data[0]['owner']

    def test_searchlight_glance_images_data(self):
        """Test that all the indexed images data is served from api server"""

        self.images_plugin.index_initial_data()
        self._flush_elasticsearch(self.images_plugin.alias_name_search)
        glance_images_query = test_api.MATCH_ALL.copy()
        glance_images_query['index'] = self.images_plugin.alias_name_search
        glance_images_query['type'] = self.images_plugin.get_document_type()
        response, json_content = self._search_request(
            glance_images_query,
            self.images_owner)
        self.assertEqual(self.images_count,
                         json_content['hits']['total'])

    def test_searchlight_glance_metadefs_data(self):
        """Test that all the indexed metadefs data is served from api server"""
        self.metadefs_plugin.index_initial_data()
        self._flush_elasticsearch(self.metadefs_plugin.alias_name_search)
        metadefs_query = test_api.MATCH_ALL.copy()
        metadefs_query['index'] = self.metadefs_plugin.alias_name_search
        metadefs_query['type'] = self.metadefs_plugin.get_document_type()
        metadefs_query['sort'] = {'namespace': {'order': 'asc'}}
        response, json_content = self._search_request(metadefs_query,
                                                      self.metadefs_owner)
        self.assertEqual(self.metadefs_count,
                         json_content['hits']['total'])

    def test_es_all_data(self):
        """Test that all the data is indexed in elasticsearch server"""

        for plugin in self.images_plugin, self.metadefs_plugin:
            plugin.index_initial_data()
        self._flush_elasticsearch()
        # Test the raw elasticsearch response
        elasticsearch_docs = self._get_all_elasticsearch_docs()
        self.assertEqual(self.all_doc_count,
                         elasticsearch_docs['hits']['total'])
