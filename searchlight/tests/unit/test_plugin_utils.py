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
