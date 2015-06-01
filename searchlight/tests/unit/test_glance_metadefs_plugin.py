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

import mock
import unittest

import searchlight.tests.utils as test_utils


# Metadefinitions
TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'

NAMESPACE1 = 'namespace1'
NAMESPACE2 = 'namespace2'

PROPERTY1 = 'Property1'
PROPERTY2 = 'Property2'
PROPERTY3 = 'Property3'

OBJECT1 = 'Object1'
OBJECT2 = 'Object2'
OBJECT3 = 'Object3'

RESOURCE_TYPE1 = 'ResourceType1'
RESOURCE_TYPE2 = 'ResourceType2'
RESOURCE_TYPE3 = 'ResourceType3'

TAG1 = 'Tag1'
TAG2 = 'Tag2'
TAG3 = 'Tag3'


def _db_namespace_fixture(**kwargs):
    obj = {
        'namespace': None,
        'display_name': None,
        'description': None,
        'visibility': True,
        'protected': False,
        'owner': None
    }
    obj.update(kwargs)
    return test_utils.DictObj(**obj)


def _db_property_fixture(name, **kwargs):
    obj = {
        'name': name,
        'json_schema': {"type": "string", "title": "title"},
    }
    obj.update(kwargs)
    return test_utils.DictObj(**obj)


def _db_object_fixture(name, **kwargs):
    obj = {
        'name': name,
        'description': None,
        'json_schema': {},
        'required': '[]',
    }
    obj.update(kwargs)
    return test_utils.DictObj(**obj)


def _db_resource_type_fixture(name, **kwargs):
    obj = {
        'name': name,
        'protected': False,
    }
    obj.update(kwargs)
    return test_utils.DictObj(**obj)


def _db_namespace_resource_type_fixture(name, prefix, **kwargs):
    obj = {
        'properties_target': None,
        'prefix': prefix,
        'name': name,
    }
    obj.update(kwargs)
    return obj


def _db_tag_fixture(name, **kwargs):
    obj = {
        'name': name,
    }
    obj.update(**kwargs)
    return test_utils.DictObj(**obj)


class TestMetadefLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestMetadefLoaderPlugin, self).setUp()

        self._create_resource_types()
        self._create_namespaces()
        self._create_namespace_resource_types()
        self._create_properties()
        self._create_tags()
        self._create_objects()

        # self.plugin = metadefs_plugin.MetadefIndex()

    def _create_namespaces(self):
        self.namespaces = [
            _db_namespace_fixture(namespace=NAMESPACE1,
                                  display_name='1',
                                  description='desc1',
                                  visibility='private',
                                  protected=True,
                                  owner=TENANT1),
            _db_namespace_fixture(namespace=NAMESPACE2,
                                  display_name='2',
                                  description='desc2',
                                  visibility='public',
                                  protected=False,
                                  owner=TENANT1),
        ]

    def _create_properties(self):
        self.properties = [
            _db_property_fixture(name=PROPERTY1),
            _db_property_fixture(name=PROPERTY2),
            _db_property_fixture(name=PROPERTY3)
        ]

        self.namespaces[0].properties = [self.properties[0]]
        self.namespaces[1].properties = self.properties[1:]

    def _create_objects(self):
        self.objects = [
            _db_object_fixture(name=OBJECT1,
                               description='desc1',
                               json_schema={'property1': {
                                   'type': 'string',
                                   'default': 'value1',
                                   'enum': ['value1', 'value2']
                               }}),
            _db_object_fixture(name=OBJECT2,
                               description='desc2'),
            _db_object_fixture(name=OBJECT3,
                               description='desc3'),
        ]

        self.namespaces[0].objects = [self.objects[0]]
        self.namespaces[1].objects = self.objects[1:]

    def _create_resource_types(self):
        self.resource_types = [
            _db_resource_type_fixture(name=RESOURCE_TYPE1,
                                      protected=False),
            _db_resource_type_fixture(name=RESOURCE_TYPE2,
                                      protected=False),
            _db_resource_type_fixture(name=RESOURCE_TYPE3,
                                      protected=True),
        ]

    def _create_namespace_resource_types(self):
        self.namespace_resource_types = [
            _db_namespace_resource_type_fixture(
                prefix='p1',
                name=self.resource_types[0].name),
            _db_namespace_resource_type_fixture(
                prefix='p2',
                name=self.resource_types[1].name),
            _db_namespace_resource_type_fixture(
                prefix='p2',
                name=self.resource_types[2].name),
        ]
        self.namespaces[0].resource_types = self.namespace_resource_types[:1]
        self.namespaces[1].resource_types = self.namespace_resource_types[1:]

    def _create_tags(self):
        self.tags = [
            _db_resource_type_fixture(name=TAG1),
            _db_resource_type_fixture(name=TAG2),
            _db_resource_type_fixture(name=TAG3),
        ]
        self.namespaces[0].tags = self.tags[:1]
        self.namespaces[1].tags = self.tags[1:]

    @unittest.skip("Skipping metadefs")
    def test_index_name(self):
        self.assertEqual('glance', self.plugin.get_index_name())

    @unittest.skip("Skipping metadefs")
    def test_document_type(self):
        self.assertEqual('metadef', self.plugin.get_document_type())

    @unittest.skip("Skipping metadefs")
    def test_namespace_serialize(self):
        metadef_namespace = self.namespaces[0]
        expected = {
            'namespace': 'namespace1',
            'display_name': '1',
            'description': 'desc1',
            'visibility': 'private',
            'protected': True,
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df'
        }
        serialized = self.plugin.serialize_namespace(metadef_namespace)
        self.assertEqual(expected, serialized)

    @unittest.skip("Skipping metadefs")
    def test_object_serialize(self):
        metadef_object = self.objects[0]
        expected = {
            'name': 'Object1',
            'description': 'desc1',
            'properties': [{
                'default': 'value1',
                'enum': ['value1', 'value2'],
                'property': 'property1',
                'type': 'string'
            }]
        }
        serialized = self.plugin.serialize_object(metadef_object)
        self.assertEqual(expected, serialized)

    @unittest.skip("Skipping metadefs")
    def test_property_serialize(self):
        metadef_property = self.properties[0]
        expected = {
            'property': 'Property1',
            'type': 'string',
            'title': 'title',
        }
        serialized = self.plugin.serialize_property(
            metadef_property.name, metadef_property.json_schema)
        self.assertEqual(expected, serialized)

    @unittest.skip("Skipping metadefs")
    def test_complex_serialize(self):
        metadef_namespace = self.namespaces[0]
        expected = {
            'namespace': 'namespace1',
            'display_name': '1',
            'description': 'desc1',
            'visibility': 'private',
            'protected': True,
            'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'objects': [{
                'description': 'desc1',
                'name': 'Object1',
                'properties': [{
                    'default': 'value1',
                    'enum': ['value1', 'value2'],
                    'property': 'property1',
                    'type': 'string'
                }]
            }],
            'resource_types': [{
                'prefix': 'p1',
                'name': 'ResourceType1',
                'properties_target': None
            }],
            'properties': [{
                'property': 'Property1',
                'title': 'title',
                'type': 'string'
            }],
            'tags': [{'name': 'Tag1'}],
        }
        serialized = self.plugin.serialize(metadef_namespace)
        self.assertEqual(expected, serialized)

    @unittest.skip("Skipping metadefs")
    def test_setup_data(self):
        with mock.patch.object(self.plugin, 'get_objects',
                               return_value=self.namespaces) as mock_get:
            with mock.patch.object(self.plugin, 'save_documents') as mock_save:
                self.plugin.setup_data()

                mock_get.assert_called_once_with()
                mock_save.assert_called_once_with([
                    {
                        'display_name': '1',
                        'description': 'desc1',
                        'objects': [
                            {
                                'name': 'Object1',
                                'description': 'desc1',
                                'properties': [{
                                    'default': 'value1',
                                    'property': 'property1',
                                    'enum': ['value1', 'value2'],
                                    'type': 'string'
                                }],
                            }
                        ],
                        'namespace': 'namespace1',
                        'visibility': 'private',
                        'protected': True,
                        'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'properties': [{
                            'property': 'Property1',
                            'type': 'string',
                            'title': 'title'
                        }],
                        'resource_types': [{
                            'prefix': 'p1',
                            'name': 'ResourceType1',
                            'properties_target': None
                        }],
                        'tags': [{'name': 'Tag1'}],
                    },
                    {
                        'display_name': '2',
                        'description': 'desc2',
                        'objects': [
                            {
                                'properties': [],
                                'name': 'Object2',
                                'description': 'desc2'
                            },
                            {
                                'properties': [],
                                'name': 'Object3',
                                'description': 'desc3'
                            }
                        ],
                        'namespace': 'namespace2',
                        'visibility': 'public',
                        'protected': False,
                        'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'properties': [
                            {
                                'property': 'Property2',
                                'type': 'string',
                                'title': 'title'
                            },
                            {
                                'property': 'Property3',
                                'type': 'string',
                                'title': 'title'
                            }
                        ],
                        'resource_types': [
                            {
                                'name': 'ResourceType2',
                                'prefix': 'p2',
                                'properties_target': None,
                            },
                            {
                                'name': 'ResourceType3',
                                'prefix': 'p2',
                                'properties_target': None,
                            }
                        ],
                        'tags': [
                            {'name': 'Tag2'},
                            {'name': 'Tag3'},
                        ],
                    }
                ])
