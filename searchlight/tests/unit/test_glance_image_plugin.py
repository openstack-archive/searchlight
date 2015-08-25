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

import copy
import datetime
import mock
import six

from oslo_utils import timeutils

from searchlight.elasticsearch.plugins.glance import images as images_plugin
from searchlight.elasticsearch.plugins import openstack_clients
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
DATE1 = timeutils.isotime(DATETIME)

# General
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'
TENANT3 = '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
TENANT4 = 'c6c87f25-8a94-47ed-8c83-053c25f42df4'

# Images
UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc'
UUID3 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'
UUID4 = '6bbe7cc2-eae7-4c0f-b50d-a7160b0c6a86'

CHECKSUM = '93264c3edf5972c9f1cb309543d38a5c'


def _image_fixture(image_id, **kwargs):
    """Simulates a v2 image (which is just a dictionary)
    """
    extra_properties = kwargs.pop('extra_properties', {})

    image = {
        'id': image_id,
        'name': None,
        'visibility': 'public',
        'kernel_id': None,
        'file': 'v2/images/' + image_id,
        'checksum': None,
        'owner': None,
        'status': 'queued',
        'tags': [],
        'size': None,
        'virtual_size': None,
        'locations': [],
        'protected': False,
        'disk_format': None,
        'container_format': None,
        'min_ram': None,
        'min_disk': None,
        'created_at': DATE1,
        'updated_at': DATE1,
    }
    image.update(kwargs)
    for k, v in six.iteritems(extra_properties):
        image[k] = v
    return image


def _notification_fixture(image_id, **kwargs):
    properties = kwargs.pop('properties', {})
    notification = {
        'id': image_id,
        'name': None,
        'status': 'active',
        'virtual_size': None,
        'deleted': False,
        'disk_format': None,
        'container_format': None,
        'min_ram': None,
        'min_disk': None,
        'protected': False,
        'checksum': None,
        'owner': None,
        'is_public': True,
        'deleted_at': None,
        'size': None,
        'created_at': DATE1,
        'updated_at': DATE1,
        'properties': {}
    }
    for k, v in six.iteritems(kwargs):
        if k in notification:
            notification[k] = v
    for k, v in six.iteritems(properties):
        notification['properties'][k] = v
    return notification


class TestImageLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageLoaderPlugin, self).setUp()
        self.set_property_protections()

        self._create_images()

        self.plugin = images_plugin.ImageIndex()
        self.notification_handler = self.plugin.get_notification_handler()

        mock_ks_client = mock.Mock()
        mock_ks_client.service_catalog.url_for.return_value = \
            'http://localhost/glance/v2'
        patched_ks_client = mock.patch.object(
            openstack_clients,
            'get_keystoneclient',
            return_value=mock_ks_client
        )
        patched_ks_client.start()
        self.addCleanup(patched_ks_client.stop)

    def _create_images(self):
        self.simple_image = _image_fixture(
            UUID1, owner=TENANT1, checksum=CHECKSUM, name='simple', size=256,
            visibility='public', status='active'
        )
        self.tagged_image = _image_fixture(
            UUID2, owner=TENANT1, checksum=CHECKSUM, name='tagged', size=512,
            visibility='public', status='active', tags=['ping', 'pong'],
        )
        self.complex_image = _image_fixture(
            UUID3, owner=TENANT2, checksum=CHECKSUM, name='complex', size=256,
            visibility='public', status='active',
            extra_properties={'mysql_version': '5.6', 'hypervisor': 'lxc'}
        )
        self.members_image = _image_fixture(
            UUID3, owner=TENANT2, checksum=CHECKSUM, name='complex', size=256,
            visibility='private', status='active',
        )
        self.members_image_members = [
            {'member': TENANT1, 'deleted': False, 'status': 'accepted'},
            {'member': TENANT2, 'deleted': False, 'status': 'accepted'},
            {'member': TENANT3, 'deleted': True, 'status': 'accepted'},
            {'member': TENANT4, 'deleted': False, 'status': 'pending'},
        ]

        self.images = [self.simple_image, self.tagged_image,
                       self.complex_image, self.members_image]

    def test_index_name(self):
        self.assertEqual('searchlight', self.plugin.get_index_name())

    def test_document_type(self):
        self.assertEqual('OS::Glance::Image', self.plugin.get_document_type())

    def test_image_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'simple',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }
        serialized = self.plugin.serialize(self.simple_image)
        self.assertEqual(expected, serialized)

    def test_image_with_tags_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'tagged',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 512,
            'status': 'active',
            'tags': ['ping', 'pong'],
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }
        serialized = self.plugin.serialize(self.tagged_image)
        self.assertEqual(expected, serialized)

    def test_image_with_properties_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'hypervisor': 'lxc',
            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'mysql_version': '5.6',
            'name': 'complex',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }

        serialized = self.plugin.serialize(self.complex_image)
        self.assertEqual(expected, serialized)

    def test_image_with_members_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
            'members': ['6838eb7b-6ded-434a-882c-b344c77fe8df',
                        '2c014f32-55eb-467d-8fcb-4bd706012f81'],
            'min_disk': None,
            'min_ram': None,
            'name': 'complex',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'private',
            'created_at': DATE1,
            'updated_at': DATE1
        }

        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        return_value=self.members_image_members):
            serialized = self.plugin.serialize(self.members_image)
        self.assertEqual(expected, serialized)

    def test_setup_data(self):
        """Tests initial data load."""
        image_member_mocks = [
            self.members_image_members
        ]
        with mock.patch('glanceclient.v2.images.Controller.list',
                        return_value=self.images) as mock_list:
            with mock.patch('glanceclient.v2.image_members.Controller.list',
                            side_effect=image_member_mocks) as mock_members:
                # This is not testing the elasticsearch call, just
                # that the documents being indexed are as expected
                with mock.patch.object(
                        self.plugin,
                        'save_documents') as mock_save:
                    self.plugin.setup_data()

                    mock_list.assert_called_once_with()
                    mock_members.assert_called_once_with(
                        self.members_image['id'])

                    mock_save.assert_called_once_with([
                        {
                            'status': 'active',
                            'tags': [],
                            'container_format': None,
                            'min_ram': None,
                            'visibility': 'public',
                            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                            'min_disk': None,
                            'members': [],
                            'virtual_size': None,
                            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
                            'size': 256,
                            'name': 'simple',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'disk_format': None,
                            'protected': False,
                            'created_at': DATE1,
                            'updated_at': DATE1
                        },
                        {
                            'status': 'active',
                            'tags': ['ping', 'pong'],
                            'container_format': None,
                            'min_ram': None,
                            'visibility': 'public',
                            'members': [],
                            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                            'min_disk': None,
                            'virtual_size': None,
                            'id': 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc',
                            'size': 512,
                            'name': 'tagged',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'disk_format': None,
                            'protected': False,
                            'created_at': DATE1,
                            'updated_at': DATE1
                        },
                        {
                            'status': 'active',
                            'tags': [],
                            'container_format': None,
                            'min_ram': None,
                            'visibility': 'public',
                            'members': [],
                            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
                            'min_disk': None,
                            'virtual_size': None,
                            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
                            'size': 256,
                            'name': 'complex',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'mysql_version': '5.6',
                            'disk_format': None,
                            'protected': False,
                            'hypervisor': 'lxc',
                            'created_at': DATE1,
                            'updated_at': DATE1
                        },
                        {
                            'status': 'active',
                            'tags': [],
                            'container_format': None,
                            'min_ram': None,
                            'visibility': 'private',
                            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
                            'members': [
                                '6838eb7b-6ded-434a-882c-b344c77fe8df',
                                '2c014f32-55eb-467d-8fcb-4bd706012f81'
                            ],
                            'min_disk': None,
                            'virtual_size': None,
                            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
                            'size': 256,
                            'name': 'complex',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'disk_format': None,
                            'protected': False,
                            'created_at': DATE1,
                            'updated_at': DATE1
                        }
                    ])

    def test_image_rbac(self):
        """Test the image plugin RBAC query terms"""
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search'
        )
        rbac_query_fragment = self.plugin.get_rbac_filter(fake_request.context)
        expected_fragment = [{
            "and": [
                {
                    "or": [
                        {"term": {"owner": TENANT1}},
                        {"term": {"visibility": "public"}},
                        {"term": {"members": TENANT1}}
                    ]
                },
                {"type": {"value": "OS::Glance::Image"}},
                {"index": {"value": "searchlight"}}
            ]
        }]
        self.assertEqual(expected_fragment, rbac_query_fragment)

    def test_protected_properties(self):
        extra_props = {
            'x_foo_matcher': 'this is protected',
            'x_foo_something_else': 'this is not protected',
            'z_this_has_no_rules': 'this is protected too'
        }
        image_with_properties = _image_fixture(
            UUID1, owner=TENANT1, checksum=CHECKSUM, name='simple', size=256,
            status='active', extra_properties=extra_props
        )

        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        return_value=[]):
            serialized = self.plugin.serialize(image_with_properties)

        elasticsearch_results = {
            'hits': {
                'hits': [{
                    '_source': copy.deepcopy(serialized),
                    '_type': self.plugin.get_document_type(),
                    '_index': self.plugin.get_index_name()
                }]
            }
        }

        # Admin context
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=True
        )
        filtered_result = self.plugin.filter_result(
            elasticsearch_results, fake_request.context
        )

        # This should contain the three properties we added
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'simple',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1,
            'x_foo_matcher': 'this is protected',
            'x_foo_something_else': 'this is not protected',
            'z_this_has_no_rules': 'this is protected too'
        }

        self.assertEqual(expected,
                         filtered_result['hits']['hits'][0]['_source'])

        # Non admin user. Recreate this because the filter operation modifies
        # it in place and we want a fresh copy
        elasticsearch_results = {
            'hits': {
                'hits': [{
                    '_source': copy.deepcopy(serialized),
                    '_type': self.plugin.get_document_type(),
                    '_index': self.plugin.get_index_name()
                }]
            }
        }
        # Non admin context should miss the x_foo property
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        filtered_result = self.plugin.filter_result(
            elasticsearch_results, fake_request.context
        )

        # Should be missing two of the properties
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'simple',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1,
            'x_foo_something_else': 'this is not protected'
        }

        self.assertEqual(expected,
                         filtered_result['hits']['hits'][0]['_source'])

    def test_image_notification_serialize(self):
        notification = _notification_fixture(
            self.simple_image['id'],
            checksum=self.simple_image['checksum'],
            name=self.simple_image['name'],
            is_public=True,
            size=self.simple_image['size'],
            properties={'prop1': 'val1'},
            owner=self.simple_image['owner'])

        expected = {
            'status': 'active',
            # Tags are not contained in notifications
            # 'tags': [],
            'container_format': None,
            'min_ram': None,
            'visibility': 'public',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'min_disk': None,
            'members': [],
            'virtual_size': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'size': 256,
            'prop1': 'val1',
            'name': 'simple',
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'disk_format': None,
            'protected': False,
            'created_at': DATE1,
            'updated_at': DATE1
        }

        serialized = self.notification_handler.serialize_notification(
            notification)
        self.assertEqual(expected, serialized)

    def test_private_image_notification_serialize(self):
        """Test a notification for a private image"""
        notification = _notification_fixture(
            self.members_image['id'],
            checksum=self.members_image['checksum'],
            name=self.members_image['name'],
            is_public=False,
            size=self.members_image['size'],
            owner=self.members_image['owner'])

        expected = {
            'status': 'active',
            # Tags are not contained in notifications
            # 'tags': [],
            'container_format': None,
            'min_ram': None,
            'visibility': 'private',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'members': [
                '6838eb7b-6ded-434a-882c-b344c77fe8df',
                '2c014f32-55eb-467d-8fcb-4bd706012f81'
            ],
            'min_disk': None,
            'virtual_size': None,
            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
            'size': 256,
            'name': 'complex',
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'disk_format': None,
            'protected': False,
            'created_at': DATE1,
            'updated_at': DATE1
        }
        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        return_value=self.members_image_members):
            serialized = self.notification_handler.serialize_notification(
                notification)
        self.assertEqual(expected, serialized)
