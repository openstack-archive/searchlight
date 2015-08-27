# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import simplejson as json

from oslo_config import cfg
from searchlight.elasticsearch.plugins import openstack_clients

CONF = cfg.CONF
os_service_group = cfg.OptGroup(name='service_credentials',
                                title='Service credentials group')
CLI_OPTS = [
    cfg.StrOpt('os_username',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_USERNAME', 'searchlight'),
               help='User name to use for OpenStack service access.'),
    cfg.StrOpt('os_password',
               deprecated_group="DEFAULT",
               secret=True,
               default=os.environ.get('OS_PASSWORD', 'admin'),
               help='Password to use for OpenStack service access.'),
    cfg.StrOpt('os_tenant-id',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_TENANT_ID', ''),
               help='Tenant ID to use for OpenStack service access.'),
    cfg.StrOpt('os_tenant-name',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_TENANT_NAME', 'admin'),
               help='Tenant name to use for OpenStack service access.'),
    cfg.StrOpt('os_cacert',
               default=os.environ.get('OS_CACERT'),
               help='Certificate chain for SSL validation.'),
    cfg.StrOpt('os_auth-url',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_AUTH_URL',
                                      'http://localhost:5000/v2.0'),
               help='Auth URL to use for OpenStack service access.'),
    cfg.StrOpt('os_region-name',
               deprecated_group="DEFAULT",
               default=os.environ.get('OS_REGION_NAME'),
               help='Region name to use for OpenStack service endpoints.'),
    cfg.StrOpt('os_endpoint-type',
               default=os.environ.get('OS_ENDPOINT_TYPE', 'publicURL'),
               help='Type of endpoint in Identity service catalog to '
                    'use for communication with OpenStack services.'),
    cfg.BoolOpt('insecure',
                default=False,
                help='Disables X.509 certificate validation when an '
                     'SSL connection to Identity Service is established.')
]

IMAGES_FILE = "searchlight/tests/functional/data/load/images.json"
METADEFS_FILE = "searchlight/tests/functional/data/load/metadefs.json"
IMAGE_MEMBERS_FILE = \
    "searchlight/tests/functional/data/load/image_members.json"


def get_glance_images_and_members_with_pyclient():

    glance_client = openstack_clients.get_glanceclient()
    images = glance_client.images.list()
    images_json = json.dumps(list(images), indent=4)
    with open(IMAGES_FILE, "w") as f:
        f.write(images_json)

    image_members_dict = dict()
    images = glance_client.images.list()
    for image in images:
        if image['visibility'] != 'public':
            image_members = glance_client.image_members.list(image['id'])
            image_members_list = []
            if image_members:
                image_members_list = list(image_members)
            if len(image_members_list) > 0:
                image_members_dict[image['id']] = image_members_list
    image_members_json = json.dumps(image_members_dict, indent=4)
    with open(IMAGE_MEMBERS_FILE, "w") as f:
        f.write(image_members_json)


def get_glance_metadefs_with_pyclient():

    glance_client = openstack_clients.get_glanceclient()
    namespace_list = []
    metadefs_namespace_list = list(glance_client.metadefs_namespace.list())

    for namespace in metadefs_namespace_list:
        _namespace = glance_client.metadefs_namespace.get(
            namespace['namespace'])
        namespace_list.append(_namespace)

    metadef_namespace_json = json.dumps(namespace_list, indent=4)

    with open(METADEFS_FILE, "w") as f:
        f.write(metadef_namespace_json)


def generate():
    get_glance_images_and_members_with_pyclient()
    get_glance_metadefs_with_pyclient()

if __name__ == "__main__":
    CONF.register_group(os_service_group)
    CONF.register_opts(CLI_OPTS, group=os_service_group)
    generate()
