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
import novaclient.exceptions
import novaclient.v2.flavors

from oslo_serialization import jsonutils

from searchlight.elasticsearch.plugins import openstack_clients
from searchlight.elasticsearch.plugins import utils

LOG = logging.getLogger(__name__)


# All 'links' will also be removed
BLACKLISTED_FIELDS = set((u'progress', u'links'))
FLAVOR_ACCESS_FIELD = 'tenant_access'
FLAVOR_FIELDS_MAP = {
    'disabled': 'OS-FLV-DISABLED:disabled',
    'is_public': 'os-flavor-access:is_public',
    'ephemeral_gb': 'OS-FLV-EXT-DATA:ephemeral',
    'projects': 'tenant_access',
    'root_gb': 'disk',
    'memory_mb': 'ram'
}
FLAVOR_BLACKLISTED_FIELDS = ['vcpu_weight', 'flavorid']

EXTENDED_FIELDS = {'OS-EXT-STS:task_state': 'task_state',
                   'OS-EXT-STS:vm_state': 'state',
                   'OS-EXT-AZ:availability_zone': 'availability_zone',
                   'OS-EXT-SRV-ATTR:hypervisor_hostname': 'host_name',
                   'OS-EXT-SRV-ATTR:host': 'host'}


def _get_flavor_access(flavor):
    if flavor.is_public:
        return None
    try:
        n_client = openstack_clients.get_novaclient()
        return [access.tenant_id for access in
                n_client.flavor_access.list(flavor=flavor)] or None
    except novaclient.exceptions.Unauthorized:
        LOG.warning("Could not return tenant for %s; forbidden" %
                    flavor)
        return None


def serialize_nova_server(server):
    nc_client = openstack_clients.get_novaclient()
    if isinstance(server, str):
        server = nc_client.servers.get(server)

    LOG.debug("Serializing server %s for project %s",
              server.id, server.tenant_id)
    serialized = {k: v for k, v in server.to_dict().items()
                  if k not in BLACKLISTED_FIELDS}

    # Some enhancements
    serialized[u'owner'] = server.tenant_id
    serialized[u'project_id'] = server.tenant_id
    # Image is empty when the instance is booted from volume
    if isinstance(serialized[u'image'], dict):
        serialized[u'image'].pop(u'links', None)
    else:
        serialized.pop(u'image')
    serialized[u'flavor'].pop(u'links', None)

    sec_groups = serialized.pop(u'security_groups', [])
    serialized['security_groups'] = [s[u'name'] for s in sec_groups]

    _format_networks(server, serialized)

    utils.normalize_date_fields(serialized)

    serialized['status'] = serialized['status'].lower()

    # Pop the fault stracktrace if any - it's big
    fault = serialized.get('fault', None)
    if fault and isinstance(fault, dict):
        fault.pop('details', None)

    return serialized


# TODO(sjmc7) - if https://review.opendev.org/#/c/485525/ lands, remove this
# If it doesn't, make it more accurate
def _get_server_status(vm_state, task_state):
    # https://opendev.org/openstack/nova/src/branch/master/nova/api/openstack/common.py#L113
    # Simplified version of that
    if vm_state:
        vm_state = vm_state.lower()
    if task_state:
        task_state = task_state.lower()

    return {
        'active': 'active',
        'building': 'build',
        'stopped': 'shutoff',
        'resized': 'verify_resize',
        'paused': 'paused',
        'suspended': 'suspended',
        'rescued': 'rescue',
        'error': 'error',
        'deleted': 'deleted',
        'soft-delete': 'soft_deleted',
        'shelved': 'shelved',
        'shelved_offloaded': 'shelved_offloaded',
    }.get(vm_state)


def serialize_server_versioned(payload):
    # Based loosely on currently documented 1.1 InstanceActionPayload

    # Some transforms - maybe these could be made the same in nova?
    transform_keys = [('display_description', 'description'),
                      ('display_name', 'name'), ('uuid', 'id')]
    for src, dest in transform_keys:
        payload[dest] = payload.pop(src)

    copy_keys = [('tenant_id', 'project_id')]
    for src, dest in copy_keys:
        if src in payload:
            payload[dest] = payload.get(src)

    delete_keys = ['audit_period', 'node']
    for key in delete_keys:
        payload.pop(key, None)

    # We should denormalize this because it'd be better for searching
    flavor_id = payload.pop('flavor')['nova_object.data']['flavorid']
    payload['flavor'] = {'id': flavor_id}

    image_id = payload.pop('image_uuid')
    payload['image'] = {'id': image_id}

    # Translate the status, kind of. state and task_state will get
    # popped off shortly
    vm_state = payload.get('state', None)
    task_state = payload.get('task_state', None)
    payload['status'] = _get_server_status(vm_state, task_state)

    # Map backwards to the OS-EXT- attributes
    for ext_attr, simple_attr in EXTENDED_FIELDS.items():
        attribute = payload.pop(simple_attr, None)
        if attribute:
            payload[ext_attr] = attribute

    # Network information. This has to be transformed
    # TODO(sjmc7) Try to better reconcile this with the API format
    ip_addresses = [address['nova_object.data'] for address in
                    payload.pop("ip_addresses", [])]

    def map_address(addr):
        # TODO(sjmc7) Think this should be network name. Missing net type
        net = {
            "version": addr["version"],
            "name": addr["device_name"],
            "OS-EXT-IPS-MAC:mac_addr": addr["mac"],
        }
        if net["version"] == 4:
            net["ipv4_addr"] = addr["address"]
        else:
            net["ipv6_addr"] = addr["address"]
        return net

    payload["networks"] = [map_address(address) for address in ip_addresses]

    # Pop the fault stracktrace if any - it's big
    fault = payload.get('fault', None)
    if fault and isinstance(fault, dict):
        fault.pop('details', None)

    return payload


def serialize_nova_hypervisor(hypervisor, updated_at=None):
    serialized = hypervisor.to_dict()
    # The id for hypervisor is an integer, should be changed to
    # string.
    serialized['id'] = str(serialized['id'])
    # The 'cpu_info' field of hypervisor has changed from string
    # to JSON object in microversion 2.28, we should be able to
    # deal with JSON object here.
    if not isinstance(serialized['cpu_info'], dict):
        serialized['cpu_info'] = jsonutils.loads(serialized['cpu_info'])
    if not getattr(hypervisor, 'updated_at', None):
        serialized['updated_at'] = updated_at or utils.get_now_str()
    # TODO(lyj): Remove this once hypervisor notifications supported.
    for key in ['running_vms', 'vcpus_used', 'memory_mb_used', 'free_ram_mb',
                'free_disk_gb', 'local_gb_used', 'current_workload']:
        if key in serialized:
            serialized.pop(key)
    return serialized


def serialize_nova_flavor(flavor, updated_at=None):
    if hasattr(flavor, "to_dict"):
        serialized = {k: v for k, v in flavor.to_dict().items()
                      if k not in ("links")}
        serialized["extra_specs"] = flavor.get_keys()

        serialized[FLAVOR_ACCESS_FIELD] = _get_flavor_access(flavor)
    else:
        # This is a versioned flavor notification object
        serialized = copy.deepcopy(flavor)
        # Flavorid is a uuid like string.
        serialized['id'] = serialized['flavorid']
        # Extra specs and projects are added by update operation
        serialized['extra_specs'] = serialized.get('extra_specs') or {}
        serialized['projects'] = serialized.get('projects')

        # For consistent with the Flavor API response, we need to remove some
        # fields, and rename some fields key.
        for item in FLAVOR_BLACKLISTED_FIELDS:
            try:
                serialized.pop(item)
            except KeyError:
                pass

        for key, value in FLAVOR_FIELDS_MAP.items():
            try:
                serialized[value] = serialized.pop(key)
            except KeyError:
                pass

    if not serialized.get('updated_at'):
        serialized['updated_at'] = updated_at or utils.get_now_str()

    return serialized


def serialize_nova_servergroup(servergroup, updated_at=None):
    serialized = servergroup.to_dict()
    if not getattr(servergroup, 'updated_at', None):
        serialized['updated_at'] = updated_at or utils.get_now_str()
    return serialized


def _format_networks(server, serialized):
    networks = []

    # Keep the original as well
    addresses = copy.deepcopy(server.addresses)

    for net_name, ports in addresses.items():
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
