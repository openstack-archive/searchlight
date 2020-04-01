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

from oslo_serialization import jsonutils

from glanceclient.v2 import client as glance
from keystoneauth1 import session
from keystoneclient.auth.identity import v3
import novaclient.client

IMAGES_FILE = "searchlight/tests/functional/data/load/images.json"
METADEFS_FILE = "searchlight/tests/functional/data/load/metadefs.json"
IMAGE_MEMBERS_FILE = \
    "searchlight/tests/functional/data/load/image_members.json"
SERVERS_FILE = "searchlight/tests/functional/data/load/servers.json"
FLAVORS_FILE = "searchlight/tests/functional/data/load/flavors.json"
SERVER_GROUP_FILE = \
    "searchlight/tests/functional/data/load/server_groups.json"

_session = None


def _get_flavor_tenant(flavor):
    if flavor.is_public:
        return ""
    n_client = get_novaclient()
    flavor_access = n_client.flavor_access.list(flavor=flavor)[0]
    tenant_id = flavor_access.tenant_id
    return tenant_id


def _get_session():

    global _session
    if not _session:
        auth = v3.Password(auth_url=os.environ.get('OS_AUTH_URL'),
                           username=os.environ.get('OS_USERNAME'),
                           password=os.environ.get('OS_PASSWORD'),
                           tenant_name=os.environ.get('OS_TENANT_NAME'))
        ks_session = session.Session(auth=auth,
                                     verify=os.environ.get('OS_CACERT'))
    return ks_session


def get_glanceclient():
    session = _get_session()

    return glance.Client(
        session=session,
        region_name=os.environ.get('OS_REGION_NAME')
    )


def get_novaclient():
    session = _get_session()

    return novaclient.client.Client(
        version=2,
        session=session,
        region_name=os.environ.get('OS_REGION_NAME')
    )


def get_glance_images_and_members_with_pyclient():

    glance_client = get_glanceclient()
    images = glance_client.images.list()
    images_json = jsonutils.dumps(list(images), indent=4)
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
    image_members_json = jsonutils.dumps(image_members_dict, indent=4)
    with open(IMAGE_MEMBERS_FILE, "w") as f:
        f.write(image_members_json)


def get_glance_metadefs_with_pyclient():

    glance_client = get_glanceclient()
    namespace_list = []
    metadefs_namespace_list = list(glance_client.metadefs_namespace.list())

    for namespace in metadefs_namespace_list:
        _namespace = glance_client.metadefs_namespace.get(
            namespace['namespace'])
        namespace_list.append(_namespace)

    metadef_namespace_json = jsonutils.dumps(namespace_list, indent=4)

    with open(METADEFS_FILE, "w") as f:
        f.write(metadef_namespace_json)


def get_nova_servers_with_pyclient():

    nova_client = get_novaclient()
    servers = nova_client.servers.list()
    servers_list = []
    for each in servers:
        servers_list.append(each.to_dict())
    servers_json = jsonutils.dumps(list(servers_list), indent=4)
    with open(SERVERS_FILE, "w") as f:
        f.write(servers_json)


def get_nova_flavors_with_pyclient():

    nova_client = get_novaclient()
    flavor = nova_client.flavors.list()[0]
    flavor_dict = flavor.to_dict()
    flavor_dict.pop("links")
    flavor_dict.update({"tenant_id": _get_flavor_tenant(flavor)})
    flavor_dict.update({"extra_spec": flavor.get_keys()})
    flavors_json = jsonutils.dumps([flavor_dict], indent=4)
    with open(FLAVORS_FILE, "w") as f:
        f.write(flavors_json)


def get_nova_server_groups_with_pyclient():

    nova_client = get_novaclient()
    server_groups = nova_client.server_groups.list(all_projects=True)
    server_groups_list = []
    for each in server_groups:
        server_groups_list.append(each.to_dict())
        server_groups_json = jsonutils.dumps(list(server_groups_list),
                                             indent=4)
    with open(SERVERS_FILE, "w") as f:
        f.write(server_groups_json)


def generate():
    get_glance_images_and_members_with_pyclient()
    get_glance_metadefs_with_pyclient()
    get_nova_servers_with_pyclient()
    get_nova_flavors_with_pyclient()
    get_nova_server_groups_with_pyclient()


if __name__ == "__main__":
    generate()
