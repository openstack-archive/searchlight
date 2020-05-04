# Copyright 2016 Hewlett-Packard Corporation
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

import collections
import copy
import operator
import types
from unittest import mock

from oslo_config import cfg

from searchlight.common import exception
from searchlight.common import utils as searchlight_utils
from searchlight.elasticsearch import ROLE_USER_FIELD
from searchlight.tests import fake_plugins
import searchlight.tests.unit.utils as unit_test_utils
import searchlight.tests.utils as test_utils

CONF = cfg.CONF

USER1 = u'27f4d76b-be62-4e4e-aa33bb11cc55'
TENANT1 = u'4d64ac83-87af-4d2a-b884-cc42c3e8f2c0'


class TestPlugin(test_utils.BaseTestCase):
    def setUp(self):
        super(TestPlugin, self).setUp()

    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'IndexBase.mapping_use_doc_values',
                new_callable=mock.PropertyMock)
    def test_rbac_field_mapping(self, mock_use_doc_vals):
        mock_use_doc_vals.return_value = False
        mock_engine = mock.Mock()
        simple_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        simple_plugin.setup_index_mapping(index_name='fake')

        mock_engine.indices.put_mapping.assert_called_once_with(
            index='fake', doc_type='fake-simple',
            body={
                'properties': {
                    'updated_at': {'type': 'date'},
                    'id': {'type': 'string', 'index': 'not_analyzed'},
                    ROLE_USER_FIELD: {'include_in_all': False,
                                      'type': 'string',
                                      'index': 'not_analyzed'}
                }
            })

    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'IndexBase.mapping_use_doc_values',
                new_callable=mock.PropertyMock)
    def test_parent_child_mapping(self, mock_use_doc_vals):
        mock_use_doc_vals.return_value = False
        mock_engine = mock.Mock()

        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)

        child_plugin.register_parent(parent_plugin)

        parent_plugin.setup_index_mapping(index_name='fake')

        # Testing a couple of things; that
        expected_calls = [
            mock.call(
                index='fake',
                doc_type='fake-child',
                body={
                    '_parent': {'type': 'fake-simple'},
                    'properties': {
                        'updated_at': {'type': 'date'},
                        'id': {'type': 'string', 'index': 'not_analyzed'},
                        'parent_id': {'type': 'string',
                                      'index': 'not_analyzed'},
                        ROLE_USER_FIELD: {'include_in_all': False,
                                          'type': 'string',
                                          'index': 'not_analyzed'}
                    }
                }),
            mock.call(
                index='fake',
                doc_type='fake-simple',
                body={
                    'properties': {
                        'updated_at': {'type': 'date'},
                        'id': {'type': 'string', 'index': 'not_analyzed'},
                        ROLE_USER_FIELD: {'include_in_all': False,
                                          'type': 'string',
                                          'index': 'not_analyzed'}
                    }
                })
        ]
        mock_engine.indices.put_mapping.assert_has_calls(expected_calls)

        # Also test explicitly setting _parent on the child, which should
        # result in the same mapping
        mock_engine.reset_mock()
        mock_engine.indices.put_mapping.assert_not_called()

        child_mapping = child_plugin.get_mapping()

        # This mapping matches what would be assigned automatically
        def explicit_parent_mapping(_self):
            child_mapping['_parent'] = {'type': 'fake-simple'}
            return child_mapping

        child_plugin.get_mapping = types.MethodType(explicit_parent_mapping,
                                                    child_plugin)
        parent_plugin.setup_index_mapping(index_name='fake')

        mock_engine.indices.put_mapping.assert_has_calls(expected_calls)

    def test_invalid_parent_mapping(self):
        mock_engine = mock.Mock()

        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)

        child_plugin.register_parent(parent_plugin)

        child_mapping = child_plugin.get_mapping()

        def bad_parent_mapping(_self):
            child_mapping['_parent'] = {'type': 'this is not my parent'}
            return child_mapping

        # Now have the child's mapping include a bad _parent value
        child_plugin.get_mapping = types.MethodType(bad_parent_mapping,
                                                    child_plugin)
        expected_error = ("Mapping for 'fake-child' contains a _parent 'this "
                          "is not my parent' that doesn't match 'fake-simple'")
        self.assertRaisesRegex(
            exception.IndexingException,
            expected_error,
            parent_plugin.setup_index_mapping,
            index_name='fake')

    def test_doc_values(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        test_doc_value_mapping = {
            'dynamic_templates': [
                {'test': {
                    "path_match": "test.*",
                    'mapping': {'type': 'integer'}
                }}
            ],
            'properties': {
                'not_analyzed_string': {'type': 'string',
                                        'index': 'not_analyzed'},
                'analyzed_string': {'type': 'string'},
                'sortable_string': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                'no_doc_values': {'type': 'string', 'index': 'not_analyzed',
                                  'doc_values': False},
                'inttype': {'type': 'integer'},
                'datetype': {'type': 'date'},
                'booltype': {'type': 'boolean'},
                'shorttype': {'type': 'short'},
                'longtype': {'type': 'long'},
                'iptype': {'type': 'ip'},
                'nested': {
                    'type': 'nested',
                    'properties': {
                        'booltype': {'type': 'boolean'},
                        'analyzed_string': {'type': 'string'},
                        'not_analyzed_string': {'type': 'string',
                                                'index': 'not_analyzed'}
                    }
                }
            }
        }

        with mock.patch.object(plugin, 'get_mapping',
                               return_value=test_doc_value_mapping):
            # get_full_mapping is a generator
            doc_type, mapping = next(plugin.get_full_mapping())
            props = mapping['properties']

            # These fields should all have doc_values. Explicitly testing
            # for 'true' here rather than assertTrue
            for field in ('not_analyzed_string', 'inttype', 'datetype',
                          'booltype', 'shorttype', 'longtype'):
                self.assertEqual(True, props[field]['doc_values'])

            self.assertEqual(
                True, props['sortable_string']['fields']['raw']['doc_values'])

            # Check nested
            for field in ('booltype', 'not_analyzed_string'):
                self.assertEqual(
                    True, props['nested']['properties'][field]['doc_values'])

            # Check dynamic templates
            dyn_mapping = mapping['dynamic_templates'][0]['test']['mapping']
            self.assertEqual(True, dyn_mapping['doc_values'])

            # These should not have doc_values
            self.assertNotIn('doc_values', props['analyzed_string'])
            self.assertNotIn('doc_values',
                             props['nested']['properties']['analyzed_string'])

            # Test explicit setting of doc_values
            self.assertEqual(False, props['no_doc_values']['doc_values'])

    def test_rbac_field_doc_values(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        doc_Type, mapping = next(plugin.get_full_mapping())
        props = mapping['properties']
        self.assertEqual(True, props[ROLE_USER_FIELD]['doc_values'])

    def test_doc_values_property(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        doc_type, mapping = next(plugin.get_full_mapping())
        self.assertEqual(True, mapping['properties']['id']['doc_values'])

        # Test the same but disabling doc values for the plugin
        with mock.patch.object(plugin.__class__,
                               'mapping_use_doc_values',
                               new_callable=mock.PropertyMock) as conf_mock:
            conf_mock.return_value = False
            doc_type, mapping = next(plugin.get_full_mapping())
            self.assertNotIn('doc_values', mapping['properties']['id'])

    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'IndexBase.setup_index_mapping')
    def test_prepare_index(self, mock_mapping):
        """Verify Indexbase.prepare_index(). The method will verify that all
        non-analyzed mapping fields that are raw, are truly marked as raw.
        This applies to any children plugins. There should not be any
        exceptions raised. In addition, the index mappings and settings are
        created at this time. Since we have separate unit tests for verifying
        the index mappings and index settings functionality, we will verify
        only that these methods are called.
        """
        mock_engine = mock.Mock()

        # Test #1: Plugin with no children, good "raw" mapping field.
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        with mock.patch.object(plugin, 'get_mapping') as mock_map:
            mock_map.return_value = {"properties": {
                "id": {"type": "string", "index": "not_analyzed"},
                "name": {"type": "string", "fields": {
                    "raw": {"type": "string", "index": "not_analyzed"}
                }}}}

            plugin.prepare_index('fake')
            mock_mapping.assert_called_once_with(index_name='fake')

        # Test #2: Plugin with no children, bad "raw" mapping field.
        mock_mapping.reset_mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        with mock.patch.object(plugin, 'get_mapping') as mock_map:
            mock_map.return_value = {"properties": {
                "id": {"type": "string", "index": "not_analyzed"},
                "name": {"type": "string"}}}

            message = ("Field 'name' for searchlight-listener/fake-simple "
                       "must contain a subfield whose name is 'raw' for "
                       "sorting.")
            self.assertRaisesRegex(Exception, message,
                                   plugin.prepare_index, index_name='fake')
            mock_mapping.assert_not_called()

        # Test #3: Plugin with two children. No "raw" mapping fields.
        mock_mapping.reset_mock()
        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child1_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        child1_plugin.register_parent(parent_plugin)
        child2_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        child2_plugin.register_parent(parent_plugin)
        parent_plugin.prepare_index('fake')
        mock_mapping.assert_called_once_with(index_name='fake')

    @mock.patch('searchlight.elasticsearch.plugins.helper.'
                'IndexingHelper.save_documents')
    @mock.patch('searchlight.elasticsearch.plugins.base.'
                'NotificationBase.get_version')
    def test_index_initial_data(self, mock_vers, mock_save):
        mock_engine = mock.Mock()

        # Test #1: Index with two documents.
        mock_vers.return_value = '1234'
        plugin = fake_plugins.NonRoleSeparatedPlugin(es_engine=mock_engine)
        plugin.index_initial_data(index_name='fake')
        mock_save.assert_called_once_with(fake_plugins.NON_ROLE_SEPARATED_DATA,
                                          versions=['1234', '1234'],
                                          index='fake')

    def test_mapping_field_types(self):
        """Fields with identical names but different types cause problems
        because lucene doesn't differentiate on doc_type. Elasticsearch 2.x
        enforces rules during mapping that 1.x did not. This test ensures that
        for any plugins present, mappings don't conflict.
        """
        # Keep track of field names and types
        encountered = {}
        encountered_in = collections.defaultdict(list)

        # Some properties are allowed to be different.
        # See https://www.elastic.co/guide/en/elasticsearch/reference/current/
        #             breaking_20_mapping_changes.html
        ignore_props = ['copy_to', 'dynamic', 'enabled', 'ignore_above',
                        'include_in_all', 'properties']

        def merge_and_assert_conflict(resource_type, properties):
            for field_name, field_type in properties.items():

                # Ignore some properties (see above)
                for prop in ignore_props:
                    field_type.pop(prop, None)

                existing = encountered.get(field_name, {})

                if existing:
                    previous = ",".join(encountered_in[field_name])
                    params = {
                        'field_name': field_name, 'field_type': field_type,
                        'resource_type': resource_type, 'previous': previous,
                        'existing': existing}
                    message = (
                        "Field definition for '%(field_name)s' in "
                        "%(resource_type)s (%(field_type)s) does not match "
                        "that found in %(previous)s (%(existing)s") % params
                    self.assertEqual(existing, field_type, message)
                else:
                    encountered[field_name] = field_type

                encountered_in[field_name].append(resource_type)

        def verify_normalized_fields(resource_type, full_mapping):
            """Some fields need to be included in all Elasticsearch mappings.
               Mostly these fields are used bhy the UI for queries. We want
               to verify that these fields do indeed exist in all mappings.
            """
            # List of fields that are required.
            fields = ['updated_at']

            for field in fields:
                self.assertIn(field, full_mapping['properties'].keys())

        index_base = 'searchlight.elasticsearch.plugins.base.IndexBase'
        with mock.patch(index_base + '.enabled',
                        new_callable=mock.PropertyMock, return_value=True):
            plugins = searchlight_utils.get_search_plugins()
            for resource_type, plugin in plugins.items():
                props = plugin.obj.get_mapping()['properties']
                merge_and_assert_conflict(resource_type, props)
                for doc_type, mapping in plugin.obj.get_full_mapping():
                    verify_normalized_fields(doc_type, mapping)

    def test_set_child_plugin_group(self):
        """Test setting child plugin's resource_group_name while loading
        plugins
        """
        mock_engine = mock.Mock()

        parent_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        child_plugin = fake_plugins.FakeWrongGroupChildPlugin(
            es_engine=mock_engine)
        grandchild_plugin = fake_plugins.FakeWrongGroupGrandchildPlugin(
            es_engine=mock_engine)
        mock_stevedore_parent = mock.Mock()
        mock_stevedore_parent.obj = parent_plugin
        mock_stevedore_child = mock.Mock()
        mock_stevedore_child.obj = child_plugin
        mock_stevedore_grandchild = mock.Mock()
        mock_stevedore_grandchild.obj = grandchild_plugin

        with mock.patch('stevedore.extension.ExtensionManager') as mock_stev:
            manager = mock.Mock()
            manager.extensions = [mock_stevedore_parent,
                                  mock_stevedore_child,
                                  mock_stevedore_grandchild]

            mock_stev.return_value = manager
            searchlight_utils.get_search_plugins()
            self.assertEqual(grandchild_plugin.resource_group_name,
                             child_plugin.resource_group_name)
            self.assertEqual(child_plugin.resource_group_name,
                             parent_plugin.resource_group_name)

    def test_get_facets(self):
        mock_engine = mock.Mock()
        simple_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        simple_plugin.engine = mock_engine
        child_plugin = fake_plugins.FakeChildPlugin(es_engine=mock_engine)
        child_plugin.engine = mock_engine
        mock_engine.search.return_value = {'aggregations': {},
                                           'hits': {'total': 1}}
        fake_request = unit_test_utils.get_fake_request()

        meta_mapping = {
            'properties': {
                'reference_id_1': {'type': 'string', 'index': 'not_analyzed'},
                'some_key': {'type': 'integer'},
                'nested': {
                    'type': 'nested',
                    'properties': {
                        "some_key": {'type': 'string'},
                        'reference_id_2': {'type': 'string',
                                           'index': 'not_analyzed'}
                    }
                }
            },
            "_meta": {
                "reference_id_1": {
                    "resource_type": "OS::Glance::Image"
                },
                "nested.reference_id_2": {
                    "resource_type": "OS::Cinder::Snapshot"
                }
            }
        }

        # Test resource_types without parent
        with mock.patch.object(simple_plugin, 'get_mapping',
                               return_value=meta_mapping):
            facets, doc_count = simple_plugin.get_facets(fake_request.context)

            expected = [
                {
                    "type": "string",
                    "name": "reference_id_1",
                    "resource_type": "OS::Glance::Image"
                },
                {
                    "type": "string",
                    "name": "nested.reference_id_2",
                    "resource_type": "OS::Cinder::Snapshot",
                    "nested": True,
                },
                {
                    "type": "string",
                    "name": "nested.some_key",
                    "nested": True
                },
                {
                    "type": "integer",
                    "name": "some_key",
                }
            ]
            expected_list = sorted(expected, key=lambda k: k['name'])
            actual_list = sorted(facets, key=lambda k: k['name'])
            self.assertEqual(expected_list, actual_list)

        # Test resource_types with parent
        meta_mapping = {
            'properties': {
                'parent_id': {'type': 'string',
                              'index': 'not_analyzed'}
            },
            "_meta": {
                "parent_id": {
                    "resource_type": child_plugin.parent_plugin_type()
                }
            }
        }
        with mock.patch.object(child_plugin, 'get_mapping',
                               return_value=meta_mapping):
            facets, doc_count = child_plugin.get_facets(fake_request.context)
            expected = [
                {
                    "type": "string",
                    "name": "parent_id",
                    "resource_type": child_plugin.parent_plugin_type(),
                    "parent": True
                }
            ]
            self.assertEqual(expected, facets)

        # Test resource_types with parent and no explicit meta info
        meta_mapping.pop('_meta')
        with mock.patch.object(child_plugin, 'get_mapping',
                               return_value=meta_mapping):
            facets, doc_count = child_plugin.get_facets(fake_request.context)
            expected = [
                {
                    "type": "string",
                    "name": "parent_id",
                    "resource_type": child_plugin.parent_plugin_type(),
                    "parent": True
                }
            ]
            self.assertEqual(expected, facets)

    def test_raw_subfield_facets(self):
        mock_engine = mock.Mock()
        simple_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        simple_plugin.engine = mock_engine
        mock_engine.search.return_value = {
            'aggregations': {
                'name': {
                    'buckets': [
                        {
                            'key': 'klopp',
                            'doc_count': 1
                        },
                        {
                            'key': 'bob',
                            'doc_count': 2
                        }]
                }
            },
            'hits': {'total': 2}
        }

        fake_request = unit_test_utils.get_fake_request(
            USER1, TENANT1, '/v1/search/facets', is_admin=True)

        raw_field_mapping = {
            'properties': {
                # not analyzed string field
                'id': {'type': 'string', 'index': 'not_analyzed'},
                # analyzed string field with a raw subfield
                'name': {
                    'type': 'string',
                    'fields': {
                        'raw': {'type': 'string', 'index': 'not_analyzed'}
                    }
                },
                # non-string field with a raw subfield
                'non_string_field': {
                    'type': 'date',
                    'fields': {
                        'raw': {'type': 'string'}
                    }
                }
            }
        }

        with mock.patch.object(simple_plugin, 'get_mapping',
                               return_value=raw_field_mapping):
            with mock.patch.object(simple_plugin.__class__,
                                   'facets_with_options',
                                   new_callable=mock.PropertyMock,
                                   return_value=('name',)):
                facets, doc_count = simple_plugin.get_facets(
                    fake_request.context, all_projects=True)
                expected = [
                    {
                        'type': 'string',
                        'name': 'id'
                    },
                    {
                        'type': 'string',
                        'name': 'name',
                        'facet_field': 'name.raw',
                        'options': [
                            {
                                'key': 'klopp',
                                'doc_count': 1
                            },
                            {
                                'key': 'bob',
                                'doc_count': 2
                            }
                        ]
                    },
                    {
                        'type': 'date',
                        'name': 'non_string_field'
                    }
                ]

                facets = sorted(facets, key=lambda facet: facet['name'])
                # Test if facets query result is as expected
                self.assertEqual(expected, facets)

                expected_body = {
                    'query': {
                        'bool': {
                            'filter': {
                                'bool': {
                                    'must': {
                                        'term': {ROLE_USER_FIELD: 'admin'}
                                    }
                                }
                            }
                        }
                    },
                    'aggs': {
                        'name': {
                            'terms': {'field': 'name.raw', 'size': 0}
                        }
                    }
                }

                # Test if engine gets called with right search query
                mock_engine.search.assert_called_with(
                    index=simple_plugin.alias_name_search,
                    doc_type=simple_plugin.get_document_type(),
                    body=expected_body,
                    ignore_unavailable=True,
                    size=0)

    def test_facet_counts(self):
        mock_engine = mock.Mock()
        plugin = fake_plugins.NonRoleSeparatedPlugin(es_engine=mock_engine)
        fake_request = unit_test_utils.get_fake_request(
            'a', 'b', '/v1/search/facets', is_admin=True
        )

        mock_engine.search.return_value = {
            "hits": {"total": 1}
        }
        facets, doc_count = plugin.get_facets(fake_request.context,
                                              include_fields=False)
        self.assertEqual([], facets)
        self.assertEqual(1, doc_count)
        call_args = mock_engine.search.call_args_list
        self.assertEqual(1, len(call_args))
        self.assertNotIn('aggs', call_args[0][1]['body'])

        mock_engine.search.reset_mock()
        mock_engine.search.return_value = {
            "aggregations": {
                "faceted": {"buckets": [{"key": 100, "doc_count": 1}]}
            },
            "hits": {"total": 1}
        }
        facets, doc_count = plugin.get_facets(fake_request.context,
                                              include_fields=True)

        self.assertEqual(
            [{"name": "faceted",
              "type": "short",
              "options": [{"key": 100, "doc_count": 1}]}],
            list(filter(lambda f: f["name"] == "faceted", facets)))
        self.assertEqual(1, doc_count)
        call_args = mock_engine.search.call_args_list
        self.assertEqual(1, len(call_args))
        self.assertIn('aggs', call_args[0][1]['body'])

    def test_nested_object_facets(self):
        """Check 'nested' and 'object' types are treated the same for facets"""
        mock_engine = mock.Mock()
        plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        fake_request = unit_test_utils.get_fake_request(
            'a', 'b', '/v1/search/facets', is_admin=True
        )

        mock_engine.search.return_value = {
            "hits": {"total": 1}
        }

        fake_mapping = {
            "properties": {
                "nested": {
                    "type": "nested",
                    "properties": {"inner": {"type": "string"}}
                },
                "object": {
                    "type": "object",
                    "properties": {"inner": {"type": "string"}}
                }
            }
        }
        with mock.patch.object(plugin, 'get_mapping',
                               return_value=fake_mapping):
            facets, _ = plugin.get_facets(fake_request.context)
            facets = sorted(facets, key=operator.itemgetter("name"))
            expected = [
                {"name": "nested.inner", "type": "string", "nested": True},
                {"name": "object.inner", "type": "string", "nested": False},
            ]

            self.assertEqual(expected, facets)

    def test_facets(self):
        """If you have a weak constitution, we may want to avert your eyes
           now. We want to verify that the "exclude_options" parameter for
           facets will not result in any aggregation in the Elasticsearch
           query. The actual ES query is buried in the bowels of Searchlight.
           Instead of trying to call it directly through the searchcontroller
           and mock mutliple levels of Servers/Requests/Catalogs/etc we will
           go directly to the IndexBase call.
        """
        request = unit_test_utils.get_fake_request(is_admin=True)
        mock_engine = mock.Mock()
        simple_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)
        mock_engine.search.return_value = {"hits": {"total": 0}}
        simple_plugin._get_facet_terms(fields={},
                                       request_context=request.context,
                                       all_projects=False, limit_terms=False,
                                       exclude_options=True)
        # Verify there is no aggregation when searching Elasticsearch.
        body = {
            'query': {
                'bool': {
                    'filter': {
                        'bool': {
                            'must': {
                                'term': {'__searchlight-user-role': 'admin'}
                            }
                        }
                    }
                }
            }
        }
        mock_engine.search.assert_called_with(body=body,
                                              doc_type='fake-simple',
                                              ignore_unavailable=True,
                                              index='searchlight-search',
                                              size=0)

    def test_filter_result(self):
        """Verify that any highlighted query results will filter out
           the ROLE_USER_FIELD field.
        """
        request = unit_test_utils.get_fake_request(is_admin=True)
        mock_engine = mock.Mock()
        simple_plugin = fake_plugins.FakeSimplePlugin(es_engine=mock_engine)

        # Verify with ROLE_USER_FIELD
        hit = {"_source": {"owner": "<em>admin</em>"},
               "highlight": {
                   "owner": "<em>admin</em>",
                   "__searchlight-user-role": "<em>admin</em>"}}

        simple_plugin.filter_result(hit, request.context)
        self.assertNotIn('__searchlight-user-role', hit['highlight'])

        # Verify without ROLE_USER_FIELD
        hit = {"_source": {"owner": "<em>admin</em>"},
               "highlight": {
                   "owner": "<em>admin</em>"}}

        original_hit = copy.deepcopy(hit)
        simple_plugin.filter_result(hit, request.context)
        self.assertEqual(original_hit, hit)
