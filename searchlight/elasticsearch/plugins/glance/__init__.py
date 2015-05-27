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
from glanceclient.v1.images import Image as v1_image
import glanceclient.exc
import logging
import six
from oslo_utils import timeutils

from searchlight.elasticsearch.plugins import openstack_clients

LOG = logging.getLogger(__name__)


def serialize_glance_image(image):
    g_client = openstack_clients.get_glanceclient()
    using_v1 = False

    # If we're being asked to index an ID, retrieve the full image information
    if isinstance(image, basestring):
        image = g_client.images.get(image)

    # If a v1 image, convert to dict so we can iterate over its properties
    if isinstance(image, v1_image):
        using_v1 = True
        image = image.to_dict()
    else:
        image['visibility'] = 'public' if image.pop('is_public') else 'private'

    try:
        members = g_client.image_members.list(image['id'])
        if using_v1:
            members = [member.to_dict() for member in members]
    except glanceclient.exc.HTTPForbidden, e:
        LOG.warning("Could not list image members for %s; forbidden", image['id'])
        members = []
        pass

    fields_to_ignore = ['ramdisk_id', 'schema', 'kernel_id', 'file', 'locations']
    extra_properties = image.pop('properties', [])
    document = dict((k, v) for k, v in image.iteritems()
                    if k not in fields_to_ignore)

    document['members'] = [
       member['member'] for member in members
       if (member['status'] == 'accepted' and member['deleted'] == 0)]
    for kv in extra_properties:
        document[kv['name']] = kv['value']

    return document
