# Copyright (c) 2016 Hewlett-Packard Development Company, L.P.
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

import datetime
import logging

from searchlight.common import utils
from searchlight.elasticsearch.plugins import openstack_clients

LOG = logging.getLogger(__name__)

AUTH_PREFIX = ""
ID_SEP = "/"

# _accounts is populated when get_swift_accounts() is called; which is
# guaranteed to be called before get_swift_containers and get_swift_objects
# since account plugin is parent and grandparent of container and object
_accounts = []

dateformat = "%a, %d %b %Y %H:%M:%S %Z"


def serialize_swift_account(account):
    metadocument = {k: account.get(k, None) for k, v in account.items()
                    if k.lower().startswith("x-account-meta")}
    account_fields = ('id', 'name')
    document = {f: account.get(f, None) for f in account_fields}

    document['domain_id'] = account.get('x-account-project-domain-id', None)
    if account.get('x-timestamp'):
        timestamp = float(account.get('x-timestamp'))
        document['created_at'] = \
            utils.isotime(datetime.datetime.fromtimestamp(timestamp))

    # lakshmiS: swift get_account() doesn't include update datetime field(?)
    if account.get('updated_at'):
        document['updated_at'] = account.get('updated_at')

    document.update(metadocument)
    return document


def serialize_swift_account_notification(account):
    account['name'] = account['project_name']
    account['id'] = account['account']
    account['x-account-project-domain-id'] = account['project_domain_id']
    # Note: updated_at is included in notification payload.
    # No need to map or transform the date and its format.
    return serialize_swift_account(account)


def serialize_swift_container(container):
    metadocument = {k: container.get(k, None) for k, v in
                    container.items()
                    if k.lower().startswith("x-container-meta")}
    container_fields = ('id',
                        'name',
                        'account',
                        'account_id',
                        'x-container-read'
                        )
    document = {f: container.get(f, None) for f in container_fields}
    if container.get('x-timestamp'):
        timestamp = float(container.get('x-timestamp'))
        document['created_at'] = \
            utils.isotime(datetime.datetime.fromtimestamp(timestamp))

    # (laskhmiS) get_container doesn't include last_modified field even
    # though the swift api documentation says it returns it. Include it
    # when it starts sending it.

    # Notifications for container sends this field as 'updated_at' instead
    # of 'last_modified'.
    if container.get('updated_at'):
        document['updated_at'] = container['updated_at']

    document.update(metadocument)
    return document


def serialize_swift_container_notification(container):
    # Account Id + container name. container['account'] from notification has
    # account id value.
    container['id'] = container['account'] + ID_SEP + container['container']
    container['name'] = container['container']
    container['account_id'] = container['account']
    container['account'] = container['project_name']
    return serialize_swift_container(container)


def serialize_swift_object(sobject):
    metadocument = {k: sobject.get(k, None) for k, v in sobject.items()
                    if k.lower().startswith("x-object-meta")}
    object_fields = ('id',
                     'name',
                     'account',
                     'account_id',
                     'container',
                     'container_id',
                     'etag'
                     )
    document = {f: sobject.get(f, None) for f in object_fields}
    document['content_type'] = sobject.get('content-type', None)
    document['content_length'] = sobject.get('content-length', None)

    if sobject.get('x-timestamp'):
        timestamp = float(sobject.get('x-timestamp'))
        document['created_at'] = \
            utils.isotime(datetime.datetime.fromtimestamp(timestamp))
    if sobject.get('last-modified'):
        updated_dt = datetime.datetime.strptime(
            sobject['last-modified'], dateformat)
        document['updated_at'] = utils.isotime(updated_dt)
    document.update(metadocument)
    return document


def serialize_swift_object_notification(sobj):
    # Account id + container name
    sobj['container_id'] = sobj['account'] + ID_SEP + sobj['container']
    # Account id + container name + object name
    sobj['id'] = sobj['container_id'] + ID_SEP + sobj['object']
    sobj['name'] = sobj['object']
    sobj['account_id'] = sobj['account']
    sobj['account'] = sobj['project_name']
    return serialize_swift_object(sobj)


@openstack_clients.clear_cached_swiftclient_on_unauthorized
def _get_storage_url_prefix():
    # Extracts swift proxy url after removing the default account id
    # from the service account. Later storage_url's will be constructed
    # for each account by appending the keystone tenant id.
    try:
        storage_url = openstack_clients.get_swiftclient().get_auth()[0]
        return storage_url[:storage_url.index(AUTH_PREFIX)] + AUTH_PREFIX
    except ValueError:
        LOG.error("reseller_prefix %s not found in keystone endpoint "
                  % AUTH_PREFIX)
        raise


def get_swift_accounts(auth_prefix):
    global AUTH_PREFIX
    # TODO(lakshmiS): Add support for SERVICE_ accounts
    AUTH_PREFIX = auth_prefix
    ks_client = openstack_clients.get_keystoneclient()
    for tenant in ks_client.projects.list():
        storage_url = _get_storage_url_prefix() + tenant.id
        sclient = openstack_clients.get_swiftclient_st(storage_url)
        # 0 index has account summary
        account = sclient.get_account()[0]
        account['name'] = tenant.name
        account['id'] = auth_prefix + tenant.id

        # store it for later usage in retrieving containers
        # and objects
        account_detail = {'id': account['id'],
                          'name': tenant.name,
                          'storage.url': storage_url}
        _accounts.append(account_detail)

        yield account


def get_swift_containers():
    for account in _accounts:
        sclient = openstack_clients.get_swiftclient_st(account['storage.url'])
        # 1 index has container list
        containers = sclient.get_account()[1]
        for container in containers:
            ctr, obj = sclient.get_container(container['name'])
            ctr['id'] = account['id'] + ID_SEP + container['name']
            ctr['name'] = container['name']
            ctr['account'] = account['name']
            ctr['account_id'] = account['id']
            yield ctr


def get_swift_objects():
    for account in _accounts:
        sclient = openstack_clients.get_swiftclient_st(account['storage.url'])
        # 1 index has container list
        containers = sclient.get_account()[1]
        for sctr in containers:
            ctr, obj = sclient.get_container(sctr['name'])
            for sobject in obj:
                sobj = sclient.head_object(sctr['name'], sobject['name'])
                sobj['account'] = account['name']
                sobj['account_id'] = account['id']
                sobj['container'] = sctr['name']
                sobj['container_id'] = account['id'] + ID_SEP + sctr['name']
                sobj['id'] = sobj['container_id'] + ID_SEP + sobject['name']
                sobj['name'] = sobject['name']
                yield sobj
