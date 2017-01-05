# Copyright 2015 OpenStack Foundation
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

import itertools
import operator

from keystoneauth1 import loading

import searchlight.api.versions
import searchlight.common.config
import searchlight.common.property_utils
import searchlight.common.wsgi
import searchlight.elasticsearch
import searchlight.elasticsearch.plugins.base
import searchlight.elasticsearch.plugins.openstack_clients
import searchlight.listener


def list_opts():
    return [
        ('DEFAULT',
         itertools.chain(searchlight.common.property_utils.property_opts,
                         searchlight.common.config.common_opts)),
        ('elasticsearch', searchlight.elasticsearch.search_opts),
        ('service_credentials',
         itertools.chain(
             searchlight.elasticsearch.plugins.openstack_clients.client_opts,
             loading.get_auth_common_conf_options(),
             list_auth_opts())),
        ('resource_plugin',
         searchlight.elasticsearch.plugins.base.indexer_opts),
        ('paste_deploy', searchlight.common.config.paste_deploy_opts),
        ('profiler', searchlight.common.wsgi.profiler_opts),
        ('listener', searchlight.listener.listener_opts),
        ('api',
         itertools.chain(searchlight.api.versions.versions_opts,
                         searchlight.common.wsgi.bind_opts,
                         searchlight.common.wsgi.socket_opts,
                         searchlight.common.wsgi.eventlet_opts)),
    ]


def list_auth_opts():
    # Inspired by similar code in neutron
    opt_list = []
    for plugin in ['password', 'v2password', 'v3password']:
        plugin_options = loading.get_auth_plugin_conf_options(plugin)
        for plugin_option in plugin_options:
            if all(option.name != plugin_option.name for option in opt_list):
                opt_list.append(plugin_option)

    opt_list.sort(key=operator.attrgetter('name'))
    return opt_list
