# Copyright 2016 Hewlett-Packard Enterprise Development Company, L.P.
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

import copy

from searchlight.elasticsearch.plugins import utils


def serialize_network(network, updated_at=None):
    serialized = copy.deepcopy(network)
    # TODO(sjmc7): Once subnets are added, look at whether or not to
    # leave this in dependent on what notifications are received
    serialized.pop('subnets')
    # There are no times in network requests, so we'll slap the current
    # time on for the sake of argument
    serialized['updated_at'] = updated_at or utils.get_now_str()
    return serialized


def serialize_port(port, updated_at=None):
    serialized = copy.deepcopy(port)
    serialized['updated_at'] = updated_at or utils.get_now_str()
    return serialized
