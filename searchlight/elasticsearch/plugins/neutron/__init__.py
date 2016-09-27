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


def add_rbac(network, target_tenant, policy_id):
    """Update a network based on an RBAC policy.
    """
    # Add target_tenant to members list.
    members_list = network['members']
    if target_tenant not in members_list:
        members_list.append(target_tenant)

    # Add RBAC policy.
    rbac_policy = network['rbac_policy']
    policy = {'rbac_id': policy_id, 'target_tenant': target_tenant}
    rbac_policy.append(policy)
    network['rbac_policy'] = rbac_policy


def serialize_network(network):
    serialized = copy.deepcopy(network)
    # Remove subnets because we index them separately
    serialized.pop('subnets')
    serialized['project_id'] = serialized['tenant_id']
    if 'members' not in serialized:
        serialized['members'] = []
    if 'rbac_policy' not in serialized:
        serialized['rbac_policy'] = []
    return serialized


def serialize_port(port):
    serialized = copy.deepcopy(port)
    serialized['project_id'] = serialized['tenant_id']
    return serialized


def serialize_subnet(subnet):
    serialized = copy.deepcopy(subnet)
    serialized['project_id'] = serialized['tenant_id']
    return serialized


def serialize_router(router, updated_at=None):
    serialized = copy.deepcopy(router)
    if 'updated_at' not in router:
        serialized['updated_at'] = updated_at or utils.get_now_str()
    serialized['project_id'] = serialized['tenant_id']
    return serialized


def serialize_floatingip(fip, updated_at=None):
    serialized = copy.deepcopy(fip)
    if 'updated_at' not in fip:
        serialized['updated_at'] = updated_at or utils.get_now_str()
    serialized['project_id'] = serialized['tenant_id']
    return serialized


def serialize_security_group(sec_group, updated_at=None):
    serialized = copy.deepcopy(sec_group)
    if 'updated_at' not in sec_group:
        serialized['updated_at'] = updated_at or utils.get_now_str()
    serialized['project_id'] = serialized['tenant_id']
    return serialized
