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

from elasticsearch import exceptions as es_exc
from unittest import mock

from oslo_config import cfg
import oslo_utils
import re
from searchlight.elasticsearch.plugins.base import resource_group_reg
from searchlight.elasticsearch.plugins import utils as plugin_utils
from searchlight.tests.unit import utils as unit_test_utils
from searchlight.tests import utils as test_utils

CONF = cfg.CONF
now = oslo_utils.timeutils.utcnow()
now_str = now.strftime(plugin_utils.FORMAT)


class TestPluginUtils(test_utils.BaseTestCase):
    def test_facet_value_query(self):
        fields = ['simple', 'nested.single', 'nested.list']
        field_types = ['string', 'nested', 'object']
        aggregation_query = plugin_utils.get_facets_query(fields, field_types,
                                                          10)

        expected = dict((
            unit_test_utils.simple_facet_field_agg('simple', size=10),
            unit_test_utils.complex_facet_field_agg('nested.single', size=10),
            unit_test_utils.complex_facet_field_agg('nested.list', size=10)
        ))
        self.assertEqual(expected, aggregation_query)

    def test_facet_result_transform(self):
        agg_results = {
            "simple": {
                "doc_count_error_upper_bound": 0,
                "sum_other_doc_count": 0,
                "buckets": [{"key": "VALUE1", "doc_count": 1}]
            },
            "nested.single": {
                "doc_count_error_upper_bound": 0,
                "sum_other_doc_count": 0,
                "nested.single": {
                    "buckets": [{
                        "key": "SINGLE_VALUE1",
                        "doc_count": 1,
                        "nested.single__unique_docs": {
                            "doc_count": 1
                        }
                    }]
                }
            },
            "nested.list": {
                "doc_count_error_upper_bound": 0,
                "sum_other_doc_count": 0,
                "nested.list": {
                    "doc_count_error_upper_bound": 0,
                    "sum_other_doc_count": 0,
                    "buckets": [{
                        "key": "LIST_VALUE1",
                        "doc_count": 2,
                        "nested.list__unique_docs": {
                            "doc_count": 1
                        }
                    }]
                }
            }
        }

        formatted = plugin_utils.transform_facets_results(
            agg_results,
            resource_type="fake")

        expected = {
            "simple": [
                {"key": "VALUE1", "doc_count": 1}
            ],
            "nested.single": [
                {"key": "SINGLE_VALUE1", "doc_count": 1}
            ],
            "nested.list": [
                {"key": "LIST_VALUE1", "doc_count": 1}
            ]
        }

        self.assertEqual(expected, formatted)

    def test_timestamp_conversion(self):
        timestamp = '2016-02-17 18:48:01.252228'
        converted = plugin_utils.timestamp_to_isotime(timestamp)
        self.assertEqual('2016-02-17T18:48:01Z', converted)

    def test_get_refresh_interval(self):
        mock_engine = mock.Mock()
        with mock.patch('searchlight.elasticsearch.get_api') as mock_api:
            mock_api.return_value = mock_engine

            # Test #1: no refresh_interval is set, return default interval
            mock_engine.indices.get_settings.return_value = {}
            interval = plugin_utils.get_index_refresh_interval('test-index')
            mock_engine.indices.get_settings.assert_called_with(
                'test-index',
                'index.refresh_interval'
            )
            self.assertEqual('1s', interval)

            # Test #2: get refresh_interval already set
            mock_engine.reset_mock()
            body = {
                'text-index': {
                    'settings': {
                        'index': {
                            'refresh_interval': '2s'}}}}
            mock_engine.indices.get_settings.return_value = body
            interval = plugin_utils.get_index_refresh_interval('text-index')
            self.assertEqual('2s', interval)

    def test_set_refresh_interval(self):
        mock_engine = mock.Mock()
        with mock.patch('searchlight.elasticsearch.get_api') as mock_api:
            mock_api.return_value = mock_engine
            plugin_utils.set_index_refresh_interval('test-index', '10s')
            expected_body = {
                'index': {
                    'refresh_interval': '10s'
                }
            }
            mock_engine.indices.put_settings.assert_called_with(expected_body,
                                                                'test-index')

    @mock.patch('searchlight.elasticsearch.get_api')
    def test_index_settings(self, mock_api):
        mock_engine = mock.Mock()
        mock_api.return_value = mock_engine

        with mock.patch.object(CONF, 'elasticsearch') as mock_settings:
            mock_settings.index_gc_deletes = '100s'
            mock_settings.index_settings = {
                'key1': 'value1',
                'index.key2': 'value2',
                'index.something.key3': 'value3'
            }

            with mock.patch('oslo_utils.timeutils.utcnow', return_value=now):
                plugin_utils.create_new_index('test')

        expected = {
            'index': {
                'key1': 'value1',
                'key2': 'value2',
                'something.key3': 'value3',
                'gc_deletes': '100s'
            }
        }
        mock_engine.indices.create.assert_called_with(index='test-' + now_str,
                                                      body=expected)

    @mock.patch('searchlight.elasticsearch.get_api')
    def test_no_index_settings(self, mock_api):
        mock_engine = mock.Mock()
        mock_api.return_value = mock_engine

        with mock.patch('searchlight.elasticsearch.plugins.'
                        'utils._get_index_settings_from_config',
                        return_value={}):
            with mock.patch('oslo_utils.timeutils.utcnow', return_value=now):
                plugin_utils.create_new_index('test')

        mock_engine.indices.create.assert_called_with(index='test-' + now_str)

    def test_verify_index_name(self):
        """Test resource group name configuration.
           Group name must only contain lowercase alphanumeric characters
           and underscores. The first character cannot be an underscore.
        """

        invalid_names = [
            '_abc',
            '__abc',
            'abc*',
            'abc!',
            'Abc'
        ]
        for name in invalid_names:
            self.assertEqual(
                None,
                re.match(resource_group_reg, name))

        valid_names = [
            'abc',
            'abc_'
            'a'
        ]
        for name in valid_names:
            self.assertIsNotNone(re.match(resource_group_reg, name))

    def test_find_missing_types(self):
        with mock.patch((
                'searchlight.elasticsearch.plugins.utils.searchlight'
                '.elasticsearch.get_api')) as mock_api:

            mock_engine = mock.Mock()
            mock_api.return_value = mock_engine
            # Test no mapping exists
            mock_engine.indices.get_mapping.return_value = {}
            results = plugin_utils.find_missing_types(
                {
                    'index': ['OS::Nova::Server',
                              'OS::Neutron::Subnet']
                }
            )
            mock_engine.indices.get_mapping.assert_called()
            self.assertEqual(
                (set([]), set(['OS::Nova::Server', 'OS::Neutron::Subnet'])),
                results
            )

            mock_engine.reset_mock()
            # Test no index exists
            mock_engine.indices.get_mapping.side_effect = \
                es_exc.NotFoundError()
            results = plugin_utils.find_missing_types(
                {
                    'searchlight-search': ['OS::Nova::Server']
                }
            )
            mock_engine.indices.get_mapping.assert_called()
            self.assertEqual(
                (set(['searchlight-search']), set([])),
                results)
