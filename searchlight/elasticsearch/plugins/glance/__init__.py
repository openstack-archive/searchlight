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
import logging
import six
from oslo_utils import timeutils

from searchlight.elasticsearch.plugins import openstack_clients

LOG = logging.getLogger(__name__)


def serialize_glance_image(image):
    g_client = openstack_clients.get_glanceclient()
    # If this came from notifications it'll either be an image id
    # or a dictionary. Either way, there's not enough information.
    if isinstance(image, basestring):
        image = g_client.images.get(image)
    elif isinstance(image, dict):
        # Not sure this is necessary - does the 'list image' API
        # return everything we need?
        image = g_client.images.get(image['id'])

    try:
        members = list(g_client.image_members.list(image.id))
    except glanceclient.exc.HTTPForbidden, e:
        LOG.warning("Could not list image members for %s; forbidden", image.id)
        members = []
        pass

    fields_to_ignore = ['ramdisk_id', 'schema', 'kernel_id', 'file']
    document = dict((k, v) for k, v in image.iteritems()
                    if k not in fields_to_ignore)

    document['members'] = [
        member.member for member in members
        if (member.status == 'accepted' and member.deleted == 0)]

    return document
