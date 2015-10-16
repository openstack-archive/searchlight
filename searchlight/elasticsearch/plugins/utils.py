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

import logging
import six

from searchlight import i18n

LOG = logging.getLogger(__name__)
_LW = i18n._LW


def normalize_date_fields(document,
                          created_at='created',
                          updated_at='updated'):
    """Attempt to normalize documents to make it easier for consumers,
    particularly around sorting.
    """
    if created_at and 'created_at' not in document:
        document[u'created_at'] = document[created_at]
    if updated_at and 'updated_at' not in document:
        document[u'updated_at'] = document[updated_at]


def get_facets_query(fields, limit_terms):
    term_aggregations = {}
    for facet in fields:
        if isinstance(facet, tuple):
            facet_name, actual_field = facet
        else:
            facet_name, actual_field = facet, facet
        if '.' in facet_name:
            # Needs a nested aggregate
            term_aggregations[facet_name] = {
                "nested": {"path": facet_name.split('.')[0]},
                "aggs": {
                    # TODO(sjmc7): Handle deeper nesting?

                    facet_name: {
                        'terms': {
                            'field': actual_field,
                            'size': limit_terms
                        },
                        "aggs": {
                            facet_name + '__unique_docs': {
                                "reverse_nested": {}
                            }
                        }
                    }
                }
            }
        else:
            term_aggregations[facet_name] = {
                'terms': {'field': actual_field, 'size': limit_terms}
            }
    return term_aggregations


def transform_facets_results(result_aggregations, resource_type):
    """This effectively reverses the logic from `get_facets_query`,
    and produces output that looks the same regardless of whether
    a faceted field happens to be nested.

    The input should be the value of the `aggregations` keypair in the
    Elasticsearch response. Inputs can be of two forms:
      {"not_nested": {"buckets": [{"key": "something", "doc_count": 10}..]},
       "nested": "buckets": [
          {"key": 4, "doc_count": 2, "nested__unique_docs": {"doc_count": 1}},
          {"key": 6, "doc_count": 3, "nested__unique_docs": {"doc_count": 2}}
      ]}

    Output is normalized (using the __unique_docs count) to:
      {"not_nested": {"buckets": [{"key": "something", "doc_count": 10}..]},
       "nested": {"buckets": [
          {"key": 4, "doc_count": 1},
          {"key": 6, "doc_count": 2}
       ]}
    """
    facet_terms = {}
    for term, aggregation in six.iteritems(result_aggregations):
        if term in aggregation:
            # Again, deeper nesting question
            term_buckets = aggregation[term]['buckets']
            for bucket in term_buckets:
                reversed_agg = bucket.pop(term + "__unique_docs")
                bucket["doc_count"] = reversed_agg["doc_count"]
            facet_terms[term] = term_buckets
        elif 'buckets' in aggregation:
            facet_terms[term] = aggregation['buckets']
        else:
            # This can happen when there's no mapping defined at all..
            format_msg = {
                'field': term,
                'resource_type': resource_type
            }
            LOG.warning(_LW(
                "Unexpected aggregation structure for field "
                "'%(field)s' in %(resource_type)s. Is the mapping "
                "defined correctly?") % format_msg)
            facet_terms[term] = []
    return facet_terms
