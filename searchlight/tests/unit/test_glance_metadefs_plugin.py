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
import datetime
from unittest import mock

from searchlight.elasticsearch.plugins.base import NotificationBase
from searchlight.elasticsearch.plugins.glance import metadefs as md_plugin
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils

# Metadefinitions
USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'

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

now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


# TODO(sjmc7): Move this stuff to a fixtures module. These should match
# responses from the glance v2 API
def _namespace_fixture(**kwargs):
    obj = {
        'created_at': now,
        'updated_at': now,
        'namespace': None,
        'display_name': None,
        'description': None,
        'visibility': 'public',
        'protected': True,
        'owner': None,
        'schema': '/v2/schemas/metadefs/namespace',
        'resource_type_associations': [],
        'tags': [],
        'objects': [],
        'properties': {}
    }
    obj.update(kwargs)
    return obj


def _property_fixture(title, **kwargs):
    obj = {
        'description': None,
        'title': title,
        'type': 'string'
    }
    obj.update(kwargs)
    return obj


def _object_fixture(name, **kwargs):
    obj = {
        'name': name,
        'description': None,
        'properties': {}
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

        mock_session = mock.Mock()
        mock_session.get_endpoint.return_value = 'http://localhost/glance/v2'
        patched_ses = mock.patch(
            'searchlight.elasticsearch.plugins.openstack_clients._get_session',
            return_value=mock_session)
        patched_ses.start()
        self.addCleanup(patched_ses.stop)

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
            _property_fixture('title1'),
            _property_fixture('title2'),
            _property_fixture('title3')
        ]

        self.namespaces[0]['properties'] = {
            PROPERTY1: properties[0]
        }
        self.namespaces[1]['properties'] = {
            PROPERTY2: properties[1],
            PROPERTY3: properties[2]
        }

    def _create_objects(self):
        objects = [
            _object_fixture(name=OBJECT1,
                            description='desc1',
                            properties={
                                'property1': _property_fixture(
                                    'something title',
                                    type='string',
                                    enum=['value1', 'value2'],
                                    default='value1')
                            }),
            _object_fixture(name=OBJECT2,
                            description='desc2'),
            _object_fixture(name=OBJECT3,
                            description='desc3'),
        ]

        self.namespaces[0]['objects'] = objects[:1]
        self.namespaces[1]['objects'] = objects[1:]

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
        resource type allocations) whereas 'list' does not.
        """
        if isinstance(namespace, int):
            return self.namespaces[namespace]
        else:
            for n in self.namespaces:
                if n['namespace'] == namespace:
                    return n

    def _list_namespaces(self):
        """Return a stripped down copy of namespaces, minus tags, properties,
        objects, similar to glanceclient.
        """
        for namespace in self.namespaces:
            ns_copy = copy.deepcopy(namespace)
            del ns_copy['tags']
            del ns_copy['properties']
            del ns_copy['objects']
            yield ns_copy

    def test_resource_group_name(self):
        self.assertEqual('searchlight', self.plugin.resource_group_name)

    def test_document_type(self):
        self.assertEqual('OS::Glance::Metadef',
                         self.plugin.get_document_type())

    def test_complex_serialize(self):
        expected = {
            'created_at': now,
            'updated_at': now,
            'namespace': 'namespace1',
            'name': '1',
            'display_name': '1',
            'id': 'namespace1',
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
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'resource_types': [{
                # TODO(sjmc7): Removing these because i'm not sure we
                # have access to them
                # 'prefix': 'p1',
                'name': 'ResourceType1',
                # 'properties_target': None
            }],
            'properties': [{
                'name': 'Property1',
                'title': 'title1',
                'type': 'string',
                'description': None
            }],
            'tags': ['Tag1'],
        }

        ns = list(self._list_namespaces())[0]
        with mock.patch('glanceclient.v2.metadefs.NamespaceController.get',
                        return_value=self._get_namespace(ns['namespace'])):
            serialized = self.plugin.serialize(ns)
        self.assertEqual(expected, serialized)

    def test_serialize_no_tags(self):
        ns = copy.deepcopy(list(self._list_namespaces())[0])
        return_value = self._get_namespace(0)
        del return_value['tags']

        expected = {
            'created_at': now,
            'updated_at': now,
            'namespace': 'namespace1',
            'name': '1',
            'id': 'namespace1',
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
            'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
            'resource_types': [{
                # TODO(sjmc7): Removing these because i'm not sure we
                # have access to them
                # 'prefix': 'p1',
                'name': 'ResourceType1',
                # 'properties_target': None
            }],
            'properties': [{
                'name': 'Property1',
                'title': 'title1',
                'type': 'string',
                'description': None
            }],
            'tags': [],
        }
        with mock.patch('glanceclient.v2.metadefs.NamespaceController.get',
                        return_value=return_value):
            serialized = self.plugin.serialize(ns)
        self.assertEqual(expected, serialized)

    def test_index_initial_data(self):
        with mock.patch.object(self.plugin, 'get_objects',
                               return_value=self.namespaces) as mock_get:
            with mock.patch.object(self.plugin.index_helper,
                                   'save_documents') as mock_save:
                self.plugin.index_initial_data()
                versions = [NotificationBase.get_version(obj)
                            for obj in self.namespaces]
                mock_get.assert_called_once_with()
                mock_save.assert_called_once_with([
                    {
                        'created_at': now,
                        'updated_at': now,
                        'display_name': '1',
                        'description': 'desc1',
                        'id': 'namespace1',
                        'name': '1',
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
                        'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
                        'properties': [{
                            'name': 'Property1',
                            'type': 'string',
                            'title': 'title1',
                            'description': None
                        }],
                        'resource_types': [{
                            'name': 'ResourceType1',
                        }],
                        'tags': ['Tag1'],
                    },
                    {
                        'created_at': now,
                        'updated_at': now,
                        'display_name': '2',
                        'description': 'desc2',
                        'id': 'namespace2',
                        'name': '2',
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
                        'project_id': '6838eb7b-6ded-434a-882c-b344c77fe8df',
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
                        'tags': ['Tag2', 'Tag3']
                    }
                ], index=None, versions=versions)

    def test_metadef_rbac(self):
        """Test metadefs RBAC query terms"""
        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search'
        )
        rbac_filter = self.plugin.get_query_filters(fake_request.context)
        expected_fragment = {
            "indices": {
                "index": "searchlight-search",
                "no_match_query": "none",
                "query": {
                    "bool": {
                        "filter": {
                            "bool": {
                                "must": {
                                    "type": {"value": "OS::Glance::Metadef"}
                                },
                                "should": [
                                    {"term": {"owner": TENANT1}},
                                    {"term": {"visibility": "public"}},
                                ],
                                "minimum_should_match": 1
                            }
                        }
                    }
                }
            }
        }
        self.assertEqual(expected_fragment, rbac_filter)

    def test_filter_result(self):
        """We modify 'tags' to make it fit with mappings from other plugins.
        For now, we modify results to more closely fit the API.
        """
        ns = list(self._list_namespaces())[0]
        with mock.patch('glanceclient.v2.metadefs.NamespaceController.get',
                        return_value=self._get_namespace(ns['namespace'])):
            es_result = self.plugin.serialize(ns)

        self.plugin.filter_result({'_source': es_result}, None)
        self.assertEqual([{"name": "Tag1"}], es_result["tags"])
