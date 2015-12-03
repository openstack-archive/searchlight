# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

import elasticsearch
from elasticsearch import helpers
import operator
from oslo_config import cfg
import six

from searchlight.common import utils


# Fields that require special handling for sort to avoid sorting
# on tokenized values
RAW_SORT_FIELDS = ('name',)


search_opts = [
    cfg.ListOpt('hosts', default=['127.0.0.1:9200'],
                help='List of nodes where Elasticsearch instances are '
                     'running. A single node should be defined as an IP '
                     'address and port number.'),
]

CONF = cfg.CONF
CONF.register_opts(search_opts, group='elasticsearch')


def get_api():
    es_hosts = CONF.elasticsearch.hosts
    es_api = elasticsearch.Elasticsearch(hosts=es_hosts)
    return es_api


class CatalogSearchRepo(object):

    def __init__(self, context, es_api):
        self.context = context
        self.es_api = es_api
        self.plugins = utils.get_search_plugins()
        self.plugins_info_dict = self._get_plugin_info()

    def search(self, index, doc_type, query, offset,
               limit, ignore_unavailable=True, **kwargs):
        return self.es_api.search(
            index=index,
            doc_type=doc_type,
            body=query,
            from_=offset,
            size=limit,
            ignore_unavailable=ignore_unavailable,
            **kwargs)

    def index(self, default_index, default_type, actions):
        return helpers.bulk(
            client=self.es_api,
            index=default_index,
            doc_type=default_type,
            actions=actions)

    def plugins_info(self):
        return self.plugins_info_dict

    def _get_plugin_info(self):
        plugin_list = []
        for plugin_type, plugin in six.iteritems(self.plugins):
            plugin_list.append({
                'name': plugin_type,
                'type': plugin.obj.get_document_type(),
                'index': plugin.obj.get_index_name()
            })
        return {'plugins': sorted(plugin_list,
                                  key=operator.itemgetter('name'))}

    def facets(self, for_index, for_doc_type, all_projects, limit_terms):
        facets = {}
        for resource_type, plugin in six.iteritems(self.plugins):
            index_name = plugin.obj.get_index_name()
            doc_type = plugin.obj.get_document_type()
            if ((not for_index or index_name == for_index) and
                    (not for_doc_type or doc_type == for_doc_type)):
                facets[resource_type] = plugin.obj.get_facets(self.context,
                                                              all_projects,
                                                              limit_terms)
        return facets


def using_elasticsearch_v2():
    if elasticsearch.__version__[0] == 2:
        message = (
            "\n** The elasticsearch v2 python client is installed. **\n"
            "Currently Searchlight cannot clear plugin data using "
            "the v2 client.\nInstead, please manually delete any "
            "indices with data to be cleared and reindex with "
            "'--no-delete'. \nSee the developer documentation "
            "(http://docs.openstack.org/developer/searchlight/"
            "dev-environment.html) under 'Initialize the Elasticsearch "
            "Index' for details.\n\n"
            "If you are running a version 1 server, you may also install "
            "the 1.9.0 client instead of the above steps.")
        return message
    return None
