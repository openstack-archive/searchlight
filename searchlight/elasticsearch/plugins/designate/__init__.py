# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from designateclient.v2.utils import get_all
from searchlight.elasticsearch.plugins import base


def _get_zones():
    from searchlight.elasticsearch.plugins import openstack_clients
    client = openstack_clients.get_designateclient()

    return get_all(client.zones.list,
                   criterion={'all_tenants': str(True)})


def _get_recordsets(zone_id):
    from searchlight.elasticsearch.plugins import openstack_clients
    client = openstack_clients.get_designateclient()

    return get_all(client.recordsets.list,
                   criterion={'all_tenants': str(True)},
                   args=[zone_id])


def _serialize_recordset(rs):
    # NOTE: This is a hack to make project_id from tenant_id
    rs.pop("links", None)
    if "project_id" not in rs:
        rs["project_id"] = rs["tenant_id"]
    if not rs['updated_at'] and rs['created_at']:
        rs['updated_at'] = rs['created_at']
    return rs


class DesignateBase(base.IndexBase):
    @classmethod
    def get_exchanges(cls):
        return ['designate']
