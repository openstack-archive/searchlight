# Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
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

import copy
import glanceclient.exc
from glanceclient.v1.images import Image as v1_image
import logging
import six

from searchlight.elasticsearch.plugins import openstack_clients
from searchlight import i18n

LOG = logging.getLogger(__name__)
_ = i18n._
_LW = i18n._LW


def serialize_glance_image(image):
    g_client = openstack_clients.get_glanceclient()
    using_v1 = False

    # If we're being asked to index an ID, retrieve the full image information
    if isinstance(image, basestring):
        image = g_client.images.get(image)

    # TODO(lakshmiS): We shouldn't check for v1 since g_client is always v2.
    # If a v1 image, convert to dict so we can iterate over its properties
    if isinstance(image, v1_image):
        using_v1 = True
        image = image.to_dict()

    try:
        members = g_client.image_members.list(image['id'])
        # TODO(lakshmiS): Same as above. No need to check for v1.
        if using_v1:
            members = [member.to_dict() for member in members]
    except glanceclient.exc.HTTPForbidden:
        LOG.warning(_LW("Could not list image members for %s; forbidden") %
                    image['id'])
        members = []
        pass

    fields_to_ignore = ['ramdisk_id', 'schema', 'kernel_id', 'file',
                        'locations']

    document = {k: v for k, v in image.items() if k not in fields_to_ignore}

    document['members'] = [
        member['member'] for member in members
        if (member['status'] == 'accepted' and member['deleted'] == 0)]

    return document


def serialize_glance_metadef_ns(metadef_namespace):
    def _serialize_tag(tag):
        return {'name': tag['name']}

    def _serialize_property(name, property):
        serialized_prop = copy.deepcopy(property)
        serialized_prop['name'] = name
        if 'default' in serialized_prop:
            serialized_prop['default'] = str(serialized_prop['default'])
        if 'enum' in serialized_prop:
            serialized_prop['enum'] = map(str, serialized_prop['enum'])

        return serialized_prop

    def _serialize_object(obj):
        serialized_obj = {
            'name': obj['name'],
            'description': obj['description']
        }
        serialized_obj['properties'] = sorted([
            _serialize_property(name, property)
            for name, property in six.iteritems(obj.get('properties', {}))
        ])
        return serialized_obj

    def _serialize_res_type(rt):
        return {
            'name': rt['name']
        }

    # TODO(sjmc7): test this better
    incomplete = 'objects' not in metadef_namespace or \
                 'properties' not in metadef_namespace or \
                 'tags' not in metadef_namespace
    if incomplete:
        LOG.debug("Retrieving metadef namespace '%s'",
                  metadef_namespace['namespace'])
        g_client = openstack_clients.get_glanceclient()
        metadef_namespace = g_client.metadefs_namespace.get(
            metadef_namespace['namespace'])

    # The CIS code specifically serialized some fields rather than indexing
    # everything; do the same.
    namespace_fields = ('namespace', 'display_name', 'description',
                        'visibility', 'owner', 'protected')
    document = {f: metadef_namespace.get(f, None) for f in namespace_fields}

    document['tags'] = sorted([
        _serialize_tag(tag) for tag in metadef_namespace.get('tags', [])
    ])
    document['properties'] = sorted([
        _serialize_property(name, property)
        for name, property in six.iteritems(
            metadef_namespace.get('properties', {}))
    ])
    document['objects'] = sorted([
        _serialize_object(obj) for obj in metadef_namespace.get('objects', [])
    ])
    document['resource_types'] = sorted([
        _serialize_res_type(rt)
        for rt in metadef_namespace.get('resource_type_associations', [])
    ])
    return document
