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

import searchlight.common.config
import searchlight.common.property_utils
import searchlight.common.wsgi
import searchlight.elasticsearch


def list_opts():
    return [
        ('DEFAULT',
         itertools.chain(searchlight.common.wsgi.bind_opts,
                         searchlight.common.wsgi.socket_opts,
                         searchlight.common.wsgi.eventlet_opts,
                         searchlight.common.property_utils.property_opts,
                         searchlight.common.config.common_opts)),
        ('elasticsearch', searchlight.elasticsearch.search_opts),
        ('paste_deploy', searchlight.common.config.paste_deploy_opts),
        ('profiler', searchlight.common.wsgi.profiler_opts),
    ]
