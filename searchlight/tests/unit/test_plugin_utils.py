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

from searchlight.elasticsearch.plugins import utils as plugin_utils
from searchlight.tests.unit import utils as unit_test_utils
from searchlight.tests import utils as test_utils


class TestPluginUtils(test_utils.BaseTestCase):
    def test_facet_value_query(self):
        fields = ['simple', 'nested.single', 'nested.list']
        aggregation_query = plugin_utils.get_facets_query(fields, 10)

        expected = dict((
            unit_test_utils.simple_facet_field_agg('simple', size=10),
            unit_test_utils.complex_facet_field_agg('nested.single', size=10),
            unit_test_utils.complex_facet_field_agg('nested.list', size=10),
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
