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
import elasticsearch
import json
import mock
import six
import uuid

from searchlight.elasticsearch.plugins.glance import images
from searchlight.elasticsearch.plugins.glance import metadefs
from searchlight.listener import NotificationEndpoint
from searchlight.tests import functional
from searchlight.tests.functional import mock_glance_pyclient
from searchlight.tests.functional import util as futils
from searchlight.tests.utils import depends_on_exe
from searchlight.tests.utils import skip_if_disabled

MATCH_ALL = {"query": {"match_all": {}}}
IMAGES_EVENTS_FILE = "searchlight/tests/functional/data/events/images.json"
METADEF_EVENTS_FILE = "searchlight/tests/functional/data/events/metadefs.json"

OWNER1 = str(uuid.uuid4())


class TestSearchListener(functional.FunctionalTest):

    def __init__(self, *args, **kwargs):
        super(TestSearchListener, self).__init__(*args, **kwargs)
        self.image_events, self.metadef_events = self._load_events()

    @depends_on_exe("elasticsearch")
    @skip_if_disabled
    def setUp(self):
        super(TestSearchListener, self).setUp()
        self.api_server.deployment_flavor = "trusted-auth"
        # Use the role-based policy file all over; we need it for the property
        # protection tests
        self.api_server.property_protection_file = self.property_file_roles

        self.base_url = "http://127.0.0.1:%d/v1" % self.api_port
        self.start_with_retry(self.api_server,
                              "api_port",
                              max_retries=3,
                              **self.__dict__.copy())

        self.elastic_connection = elasticsearch.Elasticsearch(
            "http://localhost:%s" % self.api_server.elasticsearch_port)

        def dummy_plugin_init(plugin):
            plugin.options = mock.Mock()
            plugin.options.index_name = "searchlight"
            plugin.options.enabled = True
            plugin.options.unsearchable_fields = None

            plugin.engine = self.elastic_connection

            plugin.index_name = plugin.get_index_name()
            plugin.index_name = "searchlight"
            plugin.document_type = plugin.get_document_type()
            plugin.document_id_field = plugin.get_document_id_field()

        plugins = {
            "glance": ["images", "metadefs"]
        }
        for plugin_name, plugin_types in six.iteritems(plugins):
            for plugin_type in plugin_types:
                mod = "searchlight.elasticsearch.plugins.%s.%s.base.IndexBase" \
                      % (plugin_name, plugin_type)
                plugin_patcher = \
                    mock.patch("%s.__init__" % mod, dummy_plugin_init)
                plugin_patcher.start()
                self.addCleanup(plugin_patcher.stop)

        openstack_client_mod = "searchlight.elasticsearch.plugins." \
                               "openstack_clients.get_glanceclient"
        osclient_patcher = mock.patch(
            openstack_client_mod, mock_glance_pyclient.get_fake_glance_client
        )
        osclient_patcher.start()
        self.addCleanup(osclient_patcher.stop)

        self.images_plugin = images.ImageIndex()
        self.images_plugin.obj = self.images_plugin
        self.images_plugin.name = "image"

        self.metadefs_plugin = metadefs.MetadefIndex()
        self.metadefs_plugin.obj = self.metadefs_plugin
        self.metadefs_plugin.name = "metadef"

        self.plugins = {
            self.images_plugin.get_document_type(): self.images_plugin,
            self.metadefs_plugin.get_document_type(): self.metadefs_plugin
        }

        for plugin in self.images_plugin, self.metadefs_plugin:
            plugin.setup_index()
            plugin.setup_mapping()

        self.notification_endpoint = NotificationEndpoint(self.plugins)

    def tearDown(self):
        super(TestSearchListener, self).tearDown()

        # There"s no delete_index on the plugin class
        self.elastic_connection.indices.delete(
            index=self.images_plugin.get_index_name())
        # Ignore a 404 from metadefs because it (currently) shares and index
        self.elastic_connection.indices.delete(
            index=self.metadefs_plugin.get_index_name(),
            ignore=404)

    def _flush_elasticsearch(self, index_name=None):
        self.elastic_connection.indices.flush(index_name)

    def _load_events(self):
        with open(IMAGES_EVENTS_FILE, "r") as file:
            image_events = json.load(file)
        with open(METADEF_EVENTS_FILE, "r") as file:
            metadef_events = json.load(file)
        return image_events, metadef_events

    def _send_event_to_listener(self, event):
        event = copy.deepcopy(event)
        self.notification_endpoint.info(
            event['ctxt'],
            event['publisher_id'],
            event['event_type'],
            event['payload'],
            event['metadata']
        )
        self._flush_elasticsearch(self.images_plugin.get_index_name())
        self._flush_elasticsearch(self.metadefs_plugin.get_index_name())

    def _verify_event_processing(self, event, count=1, owner=None):
        if not owner:
            owner = event['payload']['owner']
        response, json_content = futils.search_request(
            self.base_url,
            MATCH_ALL,
            owner, "admin")
        json_content = futils.get_json(json_content)
        self.assertEqual(count, json_content['hits']['total'])
        return json_content

    def _verify_result(self, event, verification_keys, result_json):
        input = event['payload']
        result = result_json['hits']['hits'][0]['_source']
        for key in verification_keys:
            self.assertEqual(input[key], result[key])

    def test_image_create_event(self):
        """Send image.create notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event)
        result = self._verify_event_processing(create_event)
        verification_keys = ['id', 'status']
        self._verify_result(create_event, verification_keys, result)

    def test_image_update_event(self):
        """Send image.update notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event)

        update_event = self.image_events["image.update"]
        self._send_event_to_listener(update_event)
        result = self._verify_event_processing(update_event)
        verification_keys = ['name', 'protected']
        self._verify_result(update_event, verification_keys, result)

    def test_image_delete_event(self):
        """Send image.delete notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event)
        self._verify_event_processing(create_event)

        delete_event = self.image_events["image.delete"]
        self._send_event_to_listener(delete_event)
        self._verify_event_processing(delete_event, 0)

    def test_image_member_create_event(self):
        """Send member.create notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event)

        create_event = self.image_events["image.member.create"]
        self._send_event_to_listener(create_event)
        result = self._verify_event_processing(create_event, owner=OWNER1)

        # member.create event will have status of "pending" which should not
        # add the member to the image.members list
        self.assertEqual(0,
                         len(result['hits']['hits'][0]['_source']['members']))

    def test_image_member_update_event(self):
        """Send member.update notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event)

        update_event = self.image_events["image.member.update"]
        self._send_event_to_listener(update_event)
        result = self._verify_event_processing(update_event, owner=OWNER1)

        # member.update event with the status of "accepted" which should
        # add the member to the image.members list
        self.assertEqual(1,
                         len(result['hits']['hits'][0]['_source']['members']))

    def test_image_member_delete_event(self):
        """Send member.delete notification event to listener"""

        create_event = self.image_events["image.create"]
        self._send_event_to_listener(create_event)

        update_event = self.image_events["image.member.update"]
        self._send_event_to_listener(update_event)
        result = self._verify_event_processing(update_event, owner=OWNER1)
        self.assertEqual(1,
                         len(result['hits']['hits'][0]['_source']['members']))

        delete_event = self.image_events["image.member.delete"]
        self._send_event_to_listener(delete_event)
        result = self._verify_event_processing(delete_event, owner=OWNER1)

        # member.delete event should remove the member
        self.assertEqual(0,
                         len(result['hits']['hits'][0]['_source']['members']))

    def test_md_namespace_create_event(self):
        """Send metadef_namespace.create notification event to listener"""

        create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(create_event)
        result = self._verify_event_processing(create_event)
        verification_keys = ['namespace', 'display_name']
        self._verify_result(create_event, verification_keys, result)

    def test_md_namespace_update_event(self):
        """Send metadef_namespace.update notification event to listener"""

        create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(create_event)

        update_event = self.metadef_events["metadef_namespace.update"]
        self._send_event_to_listener(update_event)
        result = self._verify_event_processing(update_event)
        verification_keys = ['visibility', 'protected']
        self._verify_result(update_event, verification_keys, result)

    def test_md_namespace_delete_event(self):
        """Send metadef_namespace.delete notification event to listener"""

        create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(create_event)
        self._verify_event_processing(create_event)

        delete_event = self.metadef_events["metadef_namespace.delete"]
        self._send_event_to_listener(delete_event)
        self._verify_event_processing(delete_event, 0)

    def test_md_object_create_event(self):
        """Send metadef_object.create notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event)

        obj_create_event = self.metadef_events["metadef_object.create"]
        self._send_event_to_listener(obj_create_event)
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
        self._send_event_to_listener(ns_create_event)

        obj_create_event = self.metadef_events["metadef_object.create"]
        self._send_event_to_listener(obj_create_event)

        obj_update_event = self.metadef_events["metadef_object.update"]
        self._send_event_to_listener(obj_update_event)
        result = self._verify_event_processing(
            obj_update_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['objects'][0]
        self.assertEqual(2, len(result['properties']))

    def test_md_object_delete_event(self):
        """Send metadef_object.delete notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event)

        obj_create_event = self.metadef_events["metadef_object.create"]
        self._send_event_to_listener(obj_create_event)
        result = self._verify_event_processing(
            obj_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['objects']
        self.assertEqual(1, len(result))

        obj_delete_event = self.metadef_events["metadef_object.delete"]
        self._send_event_to_listener(obj_delete_event)
        result = self._verify_event_processing(
            obj_delete_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['objects']
        self.assertEqual(0, len(result))

    def test_md_property_create_event(self):
        """Send metadef_property.create notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event)

        prop_create_event = self.metadef_events["metadef_property.create"]
        self._send_event_to_listener(prop_create_event)
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
        self._send_event_to_listener(ns_create_event)

        prop_update_event = self.metadef_events["metadef_property.update"]
        self._send_event_to_listener(prop_update_event)
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
        self._send_event_to_listener(ns_create_event)

        prop_create_event = self.metadef_events["metadef_property.create"]
        self._send_event_to_listener(prop_create_event)
        result = self._verify_event_processing(
            prop_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['properties']
        self.assertEqual(1, len(result))

        prop_delete_event = self.metadef_events["metadef_property.delete"]
        self._send_event_to_listener(prop_delete_event)
        result = self._verify_event_processing(
            prop_delete_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['properties']
        self.assertEqual(0, len(result))

    def test_md_resource_type_create_event(self):
        """Send metadef_property.create notification event to listener"""
        ns_create_event = self.metadef_events["metadef_namespace.create"]
        self._send_event_to_listener(ns_create_event)

        res_type_create_event = \
            self.metadef_events["metadef_resource_type.create"]
        self._send_event_to_listener(res_type_create_event)
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
        self._send_event_to_listener(ns_create_event)

        res_type_create_event = \
            self.metadef_events["metadef_resource_type.create"]
        self._send_event_to_listener(res_type_create_event)
        result = self._verify_event_processing(
            res_type_create_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['resource_types']
        self.assertEqual(1, len(result))

        rs_type_delete_event = \
            self.metadef_events["metadef_resource_type.delete"]
        self._send_event_to_listener(rs_type_delete_event)
        result = self._verify_event_processing(
            rs_type_delete_event,
            owner=ns_create_event['payload']['owner'])
        result = result['hits']['hits'][0]['_source']['resource_types']
        self.assertEqual(0, len(result))
