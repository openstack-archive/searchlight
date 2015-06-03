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

import copy
import mock
import unittest

from searchlight.elasticsearch.plugins.glance import metadefs as md_plugin
from searchlight.elasticsearch.plugins import openstack_clients
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


# TODO(sjmc7): Move this stuff to a fixtures module. These should match
# responses from the glance v2 API
def _namespace_fixture(**kwargs):
    obj = {
        'namespace': None,
        'display_name': None,
        'description': None,
        'visibility': 'public',
        'protected': True,
        'owner': None,
        'schema': '/v2/schemas/metadefs/namespace',
        'resource_type_associations': [],
        'tags': [],
        'objects': []
    }
    obj.update(kwargs)
    return obj


def _property_fixture(name, **kwargs):
    obj = {
        'name': name,
        'description': None,
        'title': None,
        'type': 'string'
    }
    obj.update(kwargs)
    return obj


def _object_fixture(name, **kwargs):
    obj = {
        'name': name,
        'description': None,
        'properties': []
    }
    obj.update(kwargs)
    return obj


def _db_resource_type_fixture(name, **kwargs):
    obj = {
        'name': name,
        'protected': False,
    }
    obj.update(kwargs)
    return obj


def _namespace_resource_type_fixture(name, prefix, **kwargs):
    obj = {
        'properties_target': None,
        'prefix': prefix,
        'name': name,
    }
    obj.update(kwargs)
    return obj


def _tag_fixture(name, **kwargs):
    obj = {
        'name': name,
    }
    obj.update(**kwargs)
    return obj


class TestMetadefLoaderPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestMetadefLoaderPlugin, self).setUp()

        self._create_namespaces()
        self._create_namespace_resource_types()
        self._create_properties()
        self._create_tags()
        self._create_objects()

        self.plugin = md_plugin.MetadefIndex()

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

    def _create_namespaces(self):
        self.namespaces = [
            _namespace_fixture(namespace=NAMESPACE1,
                                  display_name='1',
                                  description='desc1',
                                  visibility='private',
                                  protected=True,
                                  owner=TENANT1,
                                  resource_type_associations=[
                                      {"name": RESOURCE_TYPE1}
                                  ]),
            _namespace_fixture(namespace=NAMESPACE2,
                                  display_name='2',
                                  description='desc2',
                                  visibility='public',
                                  protected=False,
                                  owner=TENANT1,
                                  resource_type_associations=[
                                      {"name": RESOURCE_TYPE2},
                                      {"name": RESOURCE_TYPE3}
                                  ]),
        ]

    def _create_properties(self):
        properties = [
            _property_fixture(name=PROPERTY1, title='title1'),
            _property_fixture(name=PROPERTY2, title='title2'),
            _property_fixture(name=PROPERTY3, title='title3')
        ]

        self.namespaces[0]['properties'] = properties[:1]
        self.namespaces[1]['properties'] = properties[1:]

    def _create_objects(self):
        objects = [
            _object_fixture(name=OBJECT1,
                               description='desc1',
                               properties=[_property_fixture(
                                   name='property1',
                                   type='string',
                                   enum=['value1', 'value2'],
                                   default='value1',
                                   title='something title')]
                           ),
            _object_fixture(name=OBJECT2,
                            description='desc2'),
            _object_fixture(name=OBJECT3,
                            description='desc3'),
        ]

        self.namespaces[0]['objects'] = objects[:1]
        self.namespaces[1]['objects'] = objects[1:]

    def ___create_resource_types(self):
        self.resource_types = [
            _resource_type_fixture(name=RESOURCE_TYPE1,
                                      protected=False),
            _resource_type_fixture(name=RESOURCE_TYPE2,
                                      protected=False),
            _resource_type_fixture(name=RESOURCE_TYPE3,
                                      protected=True),
        ]

    def _create_namespace_resource_types(self):
        namespace_resource_types = [
            _namespace_resource_type_fixture(
                prefix='p1',
                name=RESOURCE_TYPE1),
            _namespace_resource_type_fixture(
                prefix='p2',
                name=RESOURCE_TYPE2),
            _namespace_resource_type_fixture(
                prefix='p2',
                name=RESOURCE_TYPE3),
        ]
        self.namespaces[0]['resource_type_associations'] = \
            namespace_resource_types[:1]
        self.namespaces[1]['resource_type_associations'] = \
            namespace_resource_types[1:]

    def _create_tags(self):
        tags = [
            _tag_fixture(name=TAG1),
            _tag_fixture(name=TAG2),
            _tag_fixture(name=TAG3),
        ]
        self.namespaces[0]['tags'] = tags[:1]
        self.namespaces[1]['tags'] = tags[1:]

    def _get_namespace(self, namespace):
        """The 'get' namespace API call returns everything (objects, properties,
        resource type allocations) whereas 'list' does not"""
        if isinstance(namespace, int):
            return self.namespaces[namespace]
        else:
            return filter(lambda n: n['namespace'] == namespace,
                          self.namespaces)[0]

    def _list_namespaces(self):
        """Return a stripped down copy of namespaces, minus tags, properties,
        objects, similar to glanceclient"""
        for namespace in self.namespaces:
            ns_copy = copy.deepcopy(namespace)
            del ns_copy['tags']
            del ns_copy['properties']
            del ns_copy['objects']
            yield ns_copy

    def test_index_name(self):
        self.assertEqual('glance', self.plugin.get_index_name())

    def test_document_type(self):
        self.assertEqual('metadef', self.plugin.get_document_type())

    def test_complex_serialize(self):
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
                    'description': None,
                    'enum': ['value1', 'value2'],
                    'name': 'property1',
                    'type': 'string',
                    'title': 'something title'
                }]
            }],
            'resource_types': [{
                # TODO(sjmc7): Removing these because i'm not sure we
                # have access to them
                #'prefix': 'p1',
                'name': 'ResourceType1',
                #'properties_target': None
            }],
            'properties': [{
                'name': 'Property1',
                'title': 'title1',
                'type': 'string',
                'description': None
            }],
            'tags': [{'name': 'Tag1'}],
        }

        ns = list(self._list_namespaces())[0]
        with mock.patch('glanceclient.v2.metadefs.NamespaceController.get',
                               return_value=self._get_namespace(ns['namespace'])):
            serialized = self.plugin.serialize(ns)
        self.assertEqual(expected, serialized)

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
                                    'name': 'property1',
                                    'enum': ['value1', 'value2'],
                                    'type': 'string',
                                    'title': 'something title',
                                    'description': None
                                }],
                            }
                        ],
                        'namespace': 'namespace1',
                        'visibility': 'private',
                        'protected': True,
                        'owner': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'properties': [{
                            'name': 'Property1',
                            'type': 'string',
                            'title': 'title1',
                            'description': None
                        }],
                        'resource_types': [{
                            'name': 'ResourceType1',
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
                                'name': 'Property2',
                                'type': 'string',
                                'title': 'title2',
                                'description': None
                            },
                            {
                                'name': 'Property3',
                                'type': 'string',
                                'title': 'title3',
                                'description': None
                            }
                        ],
                        'resource_types': [
                            {
                                'name': 'ResourceType2'
                            },
                            {
                                'name': 'ResourceType3'
                            }
                        ],
                        'tags': [
                            {'name': 'Tag2'},
                            {'name': 'Tag3'},
                        ],
                    }
                ])
