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

import copy
import logging
import six

from searchlight.elasticsearch.plugins import openstack_clients
from searchlight import i18n

LOG = logging.getLogger(__name__)
_ = i18n._
_LW = i18n._LW


# All 'links' will also be removed
BLACKLISTED_FIELDS = set((u'progress', u'links'))


def serialize_nova_server(server):
    nc_client = openstack_clients.get_novaclient()
    if isinstance(server, six.text_type):
        server = nc_client.servers.get(server)

    LOG.debug("Serializing server %s for project %s",
              server.id, server.tenant_id)

    serialized = {k: v for k, v in six.iteritems(server.to_dict())
                  if k not in BLACKLISTED_FIELDS}

    # Some enhancements
    serialized[u'owner'] = server.tenant_id
    serialized[u'image'].pop(u'links', None)
    serialized[u'flavor'].pop(u'links', None)

    _format_networks(server, serialized)

    return serialized


def _format_networks(server, serialized):
    networks = []

    # Keep the original as well
    addresses = copy.deepcopy(server.addresses)

    for net_name, ports in six.iteritems(addresses):
        for port in ports:

            LOG.debug("Transforming net %s port %s for server %s",
                      net_name, port, server)
            addr = {u"name": net_name}
            port_address = port.pop(u'addr')
            if port[u'version'] == 4:
                port[u'ipv4_addr'] = port_address
            elif port[u'version'] == 6:
                port[u'ipv6_addr'] = port_address
            addr.update(port)
            networks.append(addr)
    serialized[u'networks'] = networks
