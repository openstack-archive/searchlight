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
from unittest import mock

import glanceclient.exc

from searchlight.common import utils
from searchlight.elasticsearch.plugins.base import NotificationBase
from searchlight.elasticsearch.plugins.glance import images as images_plugin
from searchlight.elasticsearch import ROLE_USER_FIELD
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils


DATETIME = datetime.datetime(2012, 5, 16, 15, 27, 36, 325355)
DATE1 = utils.isotime(DATETIME)

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
UUID5 = 'KERNEL-eae7-4c0f-b50d-RAMDISK'
UUID6 = 'c69d23df-4b3e-4e61-893a-a1dd12200bd3'

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
    for k, v in extra_properties.items():
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
        'properties': {},
        'visibility': None
    }
    for k, v in kwargs.items():
        if k in notification:
            notification[k] = v
    for k, v in properties.items():
        notification['properties'][k] = v
    return notification


class TestImageLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageLoaderPlugin, self).setUp()
        self.set_property_protections()

        self._create_images()

        self.plugin = images_plugin.ImageIndex()
        self.notification_handler = self.plugin.get_notification_handler()

    def _create_images(self):
        self.simple_image = _image_fixture(
            UUID1, owner=TENANT1, checksum=CHECKSUM, name='simple', size=256,
            visibility='public', status='active'
        )
        self.snapshot_image = _image_fixture(
            UUID1, owner=TENANT1, checksum=CHECKSUM, name='snapshot1',
            size=256, visibility='public', status='active',
            extra_properties={
                'image_type': 'snapshot',
                'base_image_ref': UUID2,
                "user_id": UUID3,
                "instance_uuid": UUID4,
                "image_state": "available"
            }
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
            UUID6, owner=TENANT2, checksum=CHECKSUM, name='complex', size=256,
            visibility='shared', status='active',
        )
        self.private_image = _image_fixture(
            UUID3, owner=TENANT2, checksum=CHECKSUM, name='complex', size=256,
            visibility='private', status='active',
        )
        self.members_image_members = [
            {'member_id': TENANT1, 'status': 'accepted'},
            {'member_id': TENANT2, 'status': 'accepted'},
            {'member_id': TENANT3, 'status': 'accepted'},
            {'member_id': TENANT4, 'status': 'pending'},
        ]
        self.kernel_ramdisk_image = _image_fixture(
            UUID5, owner=TENANT1, checksum=CHECKSUM, name='kernel_ramdisk',
            size=256, visibility='public', status='active',
            kernel_id='KERNEL-ID-SEARCH-LIGHT-ROCKS',
            ramdisk_id='RAMDISK-ID-GO-BRONCOS',
        )
        self.images = [self.simple_image, self.tagged_image,
                       self.complex_image, self.members_image,
                       self.kernel_ramdisk_image, self.private_image]

    def test_resource_group_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Glance::Image', self.plugin.get_document_type())

    def test_image_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'image_type': 'image',
            'kernel_id': None,
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'simple',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
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

    def test_image_snapshot_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': UUID1,
            'kernel_id': None,
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'snapshot1',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1,
            "image_type": "snapshot",
            "base_image_ref": UUID2,
            "user_id": UUID3,
            "instance_uuid": UUID4,
            "image_state": "available",
        }
        serialized = self.plugin.serialize(self.snapshot_image)
        self.assertEqual(expected, serialized)

    def test_image_with_tags_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc',
            'image_type': 'image',
            'kernel_id': None,
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'tagged',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
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
            'image_type': 'image',
            'kernel_id': None,
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'mysql_version': '5.6',
            'name': 'complex',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'project_id': '2c014f32-55eb-467d-8fcb-4bd706012f81',
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
            'id': 'c69d23df-4b3e-4e61-893a-a1dd12200bd3',
            'image_type': 'image',
            'kernel_id': None,
            'members': ['6838eb7b-6ded-434a-882c-b344c77fe8df',
                        '2c014f32-55eb-467d-8fcb-4bd706012f81',
                        '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'],
            'min_disk': None,
            'min_ram': None,
            'name': 'complex',
            'owner': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'project_id': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'shared',
            'created_at': DATE1,
            'updated_at': DATE1
        }

        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        return_value=self.members_image_members):
            serialized = self.plugin.serialize(self.members_image)
        self.assertEqual(expected, serialized)

    def test_image_kernel_ramdisk_serialize(self):
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': UUID5,
            'image_type': 'image',
            'kernel_id': 'KERNEL-ID-SEARCH-LIGHT-ROCKS',
            'ramdisk_id': 'RAMDISK-ID-GO-BRONCOS',
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'kernel_ramdisk',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'protected': False,
            'size': 256,
            'status': 'active',
            'tags': [],
            'virtual_size': None,
            'visibility': 'public',
            'created_at': DATE1,
            'updated_at': DATE1
        }
        serialized = self.plugin.serialize(self.kernel_ramdisk_image)
        self.assertEqual(expected, serialized)

    def test_index_initial_data(self):
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
                        self.plugin.index_helper,
                        'save_documents') as mock_save:
                    self.plugin.index_initial_data()
                    versions = [NotificationBase.get_version(img)
                                for img in self.images]
                    mock_list.assert_called_once_with()
                    mock_members.assert_called_once_with(
                        self.members_image['id'])

                    mock_save.assert_called_once_with([
                        {
                            'kernel_id': None,
                            'tags': [],
                            'protected': False,
                            'min_disk': None,
                            'min_ram': None,
                            'virtual_size': None,
                            'size': 256,
                            'container_format': None,
                            'status': 'active',
                            'updated_at': '2012-05-16T15:27:36Z',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'members': [],
                            'visibility': 'public',
                            'owner': TENANT1,
                            'project_id': TENANT1,
                            'disk_format': None,
                            'name': 'simple',
                            'created_at': '2012-05-16T15:27:36Z',
                            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
                            'image_type': 'image'
                        },
                        {
                            'kernel_id': None,
                            'tags': ['ping', 'pong'],
                            'protected': False,
                            'min_disk': None,
                            'min_ram': None,
                            'virtual_size': None,
                            'size': 512,
                            'container_format': None,
                            'status': 'active',
                            'updated_at': '2012-05-16T15:27:36Z',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'members': [],
                            'visibility': 'public',
                            'owner': TENANT1,
                            'project_id': TENANT1,
                            'disk_format': None,
                            'name': 'tagged',
                            'created_at': '2012-05-16T15:27:36Z',
                            'id': 'a85abd86-55b3-4d5b-b0b4-5d0a6e6042fc',
                            'image_type': 'image'
                        },
                        {
                            'kernel_id': None,
                            'tags': [], 'protected': False,
                            'min_disk': None,
                            'min_ram': None,
                            'virtual_size': None,
                            'size': 256,
                            'container_format': None,
                            'status': 'active',
                            'updated_at': '2012-05-16T15:27:36Z',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'members': [],
                            'mysql_version': '5.6',
                            'visibility': 'public',
                            'hypervisor': 'lxc',
                            'owner': TENANT2,
                            'project_id': TENANT2,
                            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
                            'image_type': 'image',
                            'name': 'complex',
                            'created_at': '2012-05-16T15:27:36Z',
                            'disk_format': None
                        },
                        {
                            'kernel_id': None, 'tags': [],
                            'protected': False,
                            'min_disk': None,
                            'min_ram': None,
                            'virtual_size': None,
                            'size': 256,
                            'container_format': None,
                            'status': 'active',
                            'updated_at': '2012-05-16T15:27:36Z',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'members': [
                                '6838eb7b-6ded-434a-882c-b344c77fe8df',
                                '2c014f32-55eb-467d-8fcb-4bd706012f81',
                                '5a3e60e8-cfa9-4a9e-a90a-62b42cea92b8'
                            ],
                            'visibility': 'shared',
                            'owner': TENANT2,
                            'project_id': TENANT2,
                            'disk_format': None,
                            'name': 'complex',
                            'created_at': '2012-05-16T15:27:36Z',
                            'id': 'c69d23df-4b3e-4e61-893a-a1dd12200bd3',
                            'image_type': 'image'
                        },
                        {
                            'kernel_id': 'KERNEL-ID-SEARCH-LIGHT-ROCKS',
                            'tags': [], 'protected': False,
                            'min_disk': None,
                            'ramdisk_id': 'RAMDISK-ID-GO-BRONCOS',
                            'min_ram': None,
                            'virtual_size': None,
                            'size': 256,
                            'container_format': None,
                            'status': 'active',
                            'updated_at': '2012-05-16T15:27:36Z',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'members': [],
                            'visibility': 'public',
                            'owner': TENANT1,
                            'project_id': TENANT1,
                            'disk_format': None,
                            'name': 'kernel_ramdisk',
                            'created_at': '2012-05-16T15:27:36Z',
                            'id': 'KERNEL-eae7-4c0f-b50d-RAMDISK',
                            'image_type': 'image'
                        },
                        {
                            'kernel_id': None, 'tags': [],
                            'protected': False,
                            'min_disk': None,
                            'min_ram': None,
                            'virtual_size': None,
                            'size': 256,
                            'container_format': None,
                            'status': 'active',
                            'updated_at': '2012-05-16T15:27:36Z',
                            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
                            'members': [],
                            'visibility': 'private',
                            'owner': TENANT2,
                            'project_id': TENANT2,
                            'disk_format': None,
                            'name': 'complex',
                            'created_at': '2012-05-16T15:27:36Z',
                            'id': '971ec09a-8067-4bc8-a91f-ae3557f1c4c7',
                            'image_type': 'image'
                        }
                    ], index=None, versions=versions)

    def test_image_rbac(self):
        """Test the image plugin RBAC query terms"""
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search'
        )
        rbac_query_fragment = self.plugin.get_query_filters(
            fake_request.context)
        expected_fragment = {
            "indices": {
                "index": "searchlight-search",
                "no_match_query": "none",
                "query": {
                    "bool": {
                        "filter": {
                            "bool": {
                                "must": {
                                    "type": {"value": "OS::Glance::Image"}
                                },
                                "should": [
                                    {"term": {"owner": TENANT1}},
                                    {"term": {"visibility": "public"}},
                                    {"term": {"members": TENANT1}}
                                ],
                                'minimum_should_match': 1
                            }
                        }
                    }
                },
            }
        }

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
                    '_index': self.plugin.alias_name_search
                }]
            }
        }

        # Admin context
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=True
        )

        for result_hit in elasticsearch_results['hits']['hits']:
            self.plugin.filter_result(result_hit, fake_request.context)

        # This should contain the three properties we added
        expected = {
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'container_format': None,
            'disk_format': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'image_type': 'image',
            'kernel_id': None,
            'members': [],
            'min_disk': None,
            'min_ram': None,
            'name': 'simple',
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
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
                         elasticsearch_results['hits']['hits'][0]['_source'])

        # Non admin user. Recreate this because the filter operation modifies
        # it in place and we want a fresh copy
        elasticsearch_results = {
            'hits': {
                'hits': [{
                    '_source': copy.deepcopy(serialized),
                    '_type': self.plugin.get_document_type(),
                    '_index': self.plugin.alias_name_search
                }]
            }
        }
        # Non admin context should miss the x_foo property
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )

        for result_hit in elasticsearch_results['hits']['hits']:
            self.plugin.filter_result(result_hit, fake_request.context)

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
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
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
                         elasticsearch_results['hits']['hits'][0]['_source'])

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
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'min_disk': None,
            'members': [],
            'virtual_size': None,
            'id': 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d',
            'image_type': 'image',
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
            'project_id': '2c014f32-55eb-467d-8fcb-4bd706012f81',
            'members': [],
            'min_disk': None,
            'virtual_size': None,
            'id': 'c69d23df-4b3e-4e61-893a-a1dd12200bd3',
            'image_type': 'image',
            'size': 256,
            'name': 'complex',
            'checksum': '93264c3edf5972c9f1cb309543d38a5c',
            'disk_format': None,
            'protected': False,
            'created_at': DATE1,
            'updated_at': DATE1,
        }
        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        return_value=self.members_image_members):
            serialized = self.notification_handler.serialize_notification(
                notification)
        self.assertEqual(expected, serialized)

    def test_facets(self):
        """Check that expected fields are faceted"""
        mock_engine = mock.Mock()
        self.plugin.engine = mock_engine
        mock_engine.search.return_value = {'aggregations': {},
                                           'hits': {'total': 0}}

        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search/facets', is_admin=False
        )

        facets, _ = self.plugin.get_facets(fake_request.context)
        facet_names = [f['name'] for f in facets]

        # Glance has no nested fields but owner and project id are excluded for
        # non admins
        expected_facet_names = self.plugin.get_mapping()['properties'].keys()
        expected_facet_names = set(expected_facet_names) - set(('owner',
                                                                'project_id'))

        self.assertEqual(set(expected_facet_names), set(facet_names))

        facet_option_fields = ('disk_format', 'container_format', 'tags',
                               'visibility', 'status', 'protected',
                               'image_type', 'image_state')
        expected_agg_query = {
            'aggs': dict(unit_test_utils.simple_facet_field_agg(name)
                         for name in facet_option_fields),
            'query': {
                'bool': {
                    'filter': {
                        'bool': {
                            'must': {'term': {ROLE_USER_FIELD: 'user'}},
                            'should': [
                                {'term': {'owner': TENANT1}},
                                {'term': {'visibility': 'public'}},
                                {'term': {'members': TENANT1}}
                            ],
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

    @mock.patch('searchlight.elasticsearch.plugins.helper.IndexingHelper.'
                'delete_document')
    def test_create_or_update_exception(self, mock_delete):
        notification = _notification_fixture(
            self.members_image['id'],
            checksum=self.members_image['checksum'],
            name=self.members_image['name'],
            is_public=False,
            size=self.members_image['size'],
            owner=self.members_image['owner'],
            visibility='shared')

        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        side_effect=glanceclient.exc.NotFound):
            with mock.patch.object(
                    self.notification_handler,
                    'get_version',
                    return_value='fake_version'):
                self.notification_handler.create_or_update(
                    "image.create", notification, None)
                mock_delete.assert_called_with(
                    {'_id': self.members_image['id'],
                     '_version': 'fake_version'})

    def test_image_member_list(self):
        with mock.patch('glanceclient.v2.image_members.Controller.list',
                        return_value=self.members_image_members):
            serialized = self.plugin.serialize(self.members_image)

        # Admin context
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=True
        )
        result_hit = {'_source': copy.deepcopy(serialized)}

        # Expect to see all three tenants
        self.plugin.filter_result(result_hit, fake_request.context)
        self.assertEqual(set([TENANT1, TENANT2, TENANT3]),
                         set(result_hit['_source']['members']))

        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search', is_admin=False
        )
        result_hit = {'_source': copy.deepcopy(serialized)}

        # Tenant1 can see the image but doesn't own it
        self.plugin.filter_result(result_hit, fake_request.context)
        self.assertEqual(set([TENANT1]),
                         set(result_hit['_source']['members']))

        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT2, '/v1/search', is_admin=False
        )
        result_hit = {'_source': copy.deepcopy(serialized)}

        # Tenant2 owns the image and should see all three members
        self.plugin.filter_result(result_hit, fake_request.context)
        self.assertEqual(set([TENANT1, TENANT2, TENANT3]),
                         set(result_hit['_source']['members']))


class TestImageEventHandler(test_utils.BaseTestCase):
    def setUp(self):
        super(TestImageEventHandler, self).setUp()
        self.set_property_protections()

        self._create_images()

        self.plugin = images_plugin.ImageIndex()
        self.notification_handler = self.plugin.get_notification_handler()
