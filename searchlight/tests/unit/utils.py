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

"""Common utilities used in testing"""

from searchlight.common import wsgi
import searchlight.context


SOMEUSER = '54492ba0-dead-beef-be62-27f4d76b29cf'
SOMETENANT = '6838eb7b-6ded-dead-beef-b344c77fe8df'


def get_fake_request(user=SOMEUSER, tenant=SOMETENANT, path='/v1/search',
                     method='GET', is_admin=False, roles=['member'], **kwargs):
    req = wsgi.Request.blank(path)
    req.method = method

    if is_admin and 'admin' not in roles:
        roles = roles[:]
        roles.append('admin')

    context_args = {
        'user': user,
        'tenant': tenant,
        'roles': roles,
        'is_admin': is_admin,
    }
    context_args.update(**kwargs)

    req.context = searchlight.context.RequestContext(**context_args)
    return req


def simple_facet_field_agg(name, size=0):
    return name, {'terms': {'field': name, 'size': size}}


def complex_facet_field_agg(name, size=0):
    return name, {
        'aggs': {
            name: {
                'terms': {'field': name, 'size': size},
                'aggs': {
                    name + '__unique_docs': {
                        'reverse_nested': {}
                    }
                }
            }
        },
        'nested': {'path': name.split('.')[0]}
    }
