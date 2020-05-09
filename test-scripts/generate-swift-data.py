#!/usr/bin/env python

# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
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


from keystoneclient.auth.identity import v3
from keystoneclient import session
import os
import random
import string
import swiftclient
import sys

from oslo_serialization import jsonutils

container_base_name = "scale_"
object_base_name = "object_"
object_meta_choices = [None, 'These', 'Are', 'Some', 'Random', 'Words']


object_contents = (
    ("image/svg", """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="12cm" height="12cm">
    <g style="fill-opacity:0.7; stroke:black; stroke-width:0.1cm;">
        <circle cx="6cm" cy="2cm" r="100" style="fill:red;"
                transform="translate(0,50)" />
        <circle cx="6cm" cy="2cm" r="100" style="fill:blue;"
                transform="translate(70,150)" />
        <circle cx="6cm" cy="2cm" r="100" style="fill:green;"
                transform="translate(-70,150)"/>
    </g>
</svg>"""),
    ("application/json", jsonutils.dumps({"key": ["some", "json", "vals"]})),
    ("text/html", """<html><body>This is some html</body></html>"""),
    ("application/octet-stream", "This is some octet stream"),
    ("application/text", "This is some text")
)


def get_obj_content():
    """Returns a content type and some data"""
    return random.choice(object_contents)


def get_session():
    try:
        project_name = (os.environ.get('OS_PROJECT_NAME', None) or
                        os.environ['OS_TENANT_NAME'])
        auth_url = os.environ['OS_AUTH_URL']
        username = os.environ['OS_USERNAME']
        password = os.environ['OS_PASSWORD']
    except KeyError:
        print("Make sure OS_USERNAME, OS_PASSWORD and one of\n"
              "OS_PROJECT_NAME or OS_TENANT_NAME are set")
        sys.exit(1)

    auth = v3.Password(
        auth_url=auth_url,
        username=username,
        password=password,
        tenant_name=project_name
    )
    sess = session.Session(auth=auth)
    return sess


def get_storage_url(catalog):
    swift_cat = filter(lambda cat: cat['name'] == 'swift', catalog)[0]
    return swift_cat['endpoints'][0]['publicURL']


def create(number_objects, number_containers, number_directories):
    print("Creating %d objects in %d containers" %
          (number_objects, number_containers))
    auth_session = get_session()
    token = auth_session.get_token()
    auth_ref = auth_session.auth.auth_ref
    storage_url = get_storage_url(auth_ref['serviceCatalog'])
    sc = swiftclient.client

    objects_per_container = max(number_objects / number_containers, 1)
    objects_per_directory = max(objects_per_container / number_directories, 1)

    # Touch the account to make sure all is well
    sc.post_account(storage_url, token, {})

    for container_id in range(number_containers):
        container_name = container_base_name + str(container_id)
        print("Creating container %s" % container_name)
        sc.put_container(
            storage_url, token, container_name,
            headers={'X-Container-Meta-Name': 'Container %d' % container_id})

        print("Creating %d objects" % objects_per_container)

        dir_name = ''

        obj_start_id = container_id * objects_per_container
        obj_end_id = (container_id + 1) * objects_per_container
        for object_id in range(obj_start_id, obj_end_id):
            obj_path = '%s%s%d' % (dir_name, object_base_name, object_id)
            print("Creating %s %s" % (container_name, obj_path))
            content_type, content = get_obj_content()
            headers = {}
            meta_1 = random.choice(object_meta_choices)
            if meta_1:
                headers['X-Object-Meta-' + meta_1] = 'first metadata item'
                meta_2 = random.choice(object_meta_choices)
                if meta_2:
                    headers['X-Object-Meta-' + meta_2] = 'bonus metadata item'
            sc.put_object(
                storage_url, token, container_name, obj_path,
                content_type=content_type, contents=content, headers=headers)
            object_id += 1

            if object_id % objects_per_directory == 0:
                dir_name = ''.join(random.choice(string.ascii_letters)
                                   for _ in range(2)) + '/'

    print("Created %d objects in %d containers" %
          (object_id, number_containers))


def main():
    if len(sys.argv) < 2 or sys.argv == '--help':
        print("Usage: %s <num_objects> <num_containers> <num_dirs>" %
              sys.argv[0])
        print("Generates swift objects with metadata distributed amongst\n"
              "the number of containers specified, and within directories\n"
              "with short, random names to enable swift testing")
        sys.exit(0)
    number_objects = int(sys.argv[1])
    number_containers = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    number_directories = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    create(number_objects, number_containers, number_directories)


if __name__ == "__main__":
    main()
