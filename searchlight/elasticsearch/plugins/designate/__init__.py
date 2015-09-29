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


def _walk_pages(list_func, *args, **kwargs):
    while True:
        items = list_func(*args, **kwargs)
        if not items:
            break
        kwargs["marker"] = items[-1]["id"]

        for item in items:
            yield item


def _get_recordsets(zone_id, per_page=50):
    from searchlight.elasticsearch.plugins import openstack_clients
    client = openstack_clients.get_designateclient()

    recordsets = _walk_pages(
        client.recordsets.list, zone_id,
        {"all_tenants": str(True)}, limit=per_page)

    # Yield back all recordsets
    for rs in recordsets:
        yield rs


def _serialize_recordset(rs):
    # NOTE: This is a hack to make project_id from tenant_id
    rs.pop("links", None)
    rs["records"] = [{"data": i} for i in rs["records"]]
    if not rs['updated_at'] and rs['created_at']:
        rs['updated_at'] = rs['created_at']
    return rs
