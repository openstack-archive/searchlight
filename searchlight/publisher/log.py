# Copyright 2016 Intel Corporation
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

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class LogPublisher(object):

    def publish(self, item):
        LOG.info(
            'Published notification: %(event_type)s %(doc_id)s %(doc)s' % {
                'event_type': item.event_type,
                'doc_id': item.doc_id,
                'doc': getattr(item, 'doc', None)})
