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
import os

from cinderclient import client as cinder_client
from designateclient.v2 import client as designate_client
from glanceclient import client as glance_client
from keystoneclient import auth as ks_auth
from keystoneclient import session as ks_session
import keystoneclient.v2_0.client as ks_client
import neutronclient.v2_0.client as neutron_client
from novaclient import client as nova_client
import swiftclient

from oslo_config import cfg


client_opts = [
    cfg.StrOpt('os-region-name',
               default=os.environ.get('OS_REGION_NAME'),
               help='Region name to use for OpenStack service endpoints.'),
    cfg.StrOpt('os-endpoint-type',
               default=os.environ.get('OS_ENDPOINT_TYPE', 'publicURL'),
               help='Type of endpoint in Identity service catalog to '
                    'use for communication with OpenStack services.'),
]


GROUP = "service_credentials"

cfg.CONF.register_opts(client_opts, group=GROUP)

ks_session.Session.register_conf_options(cfg.CONF, GROUP)

ks_auth.register_conf_options(cfg.CONF, GROUP)

_session = None


def _get_session():
    global _session
    if not _session:
        auth = ks_auth.load_from_conf_options(cfg.CONF, GROUP)

        _session = ks_session.Session.load_from_conf_options(
            cfg.CONF, GROUP)
        _session.auth = auth
    return _session


def get_glanceclient():
    session = _get_session()

    return glance_client.Client(
        version='2',
        session=session,
        interface=cfg.CONF.service_credentials.os_endpoint_type,
        region_name=cfg.CONF.service_credentials.os_region_name
    )


def get_novaclient():
    session = _get_session()

    return nova_client.Client(
        version='2',
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name,
        endpoint_type=cfg.CONF.service_credentials.os_endpoint_type
    )


def get_designateclient():
    session = _get_session()

    return designate_client.Client(
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name,
        endpoint_type=cfg.CONF.service_credentials.os_endpoint_type
    )


def get_neutronclient():
    session = _get_session()
    return neutron_client.Client(
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name,
        endpoint_type=cfg.CONF.service_credentials.os_endpoint_type
    )


def get_cinderclient():
    session = _get_session()

    return cinder_client.Client(
        version='2',
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name,
        endpoint_type=cfg.CONF.service_credentials.os_endpoint_type
    )

# Swift still needs special handling because it doesn't support
# keystone sessions. Rather than maintain two codepaths, we'll do this
_swiftclient = None


def clear_cached_swiftclient_on_unauthorized(fn):
    def wrapper(*args, **kwargs):
        global _session
        global _swiftclient
        try:
            return fn(*args, **kwargs)
        except swiftclient.exceptions.ClientException:
            _session = None
            _swiftclient = None
            return fn(*args, **kwargs)
    return wrapper


def get_swiftclient():

    global _swiftclient
    if _swiftclient:
        return _swiftclient
    _get_session()

    service_type = 'object-store'

    os_options = {
        'service_type': service_type,
        'region_name': cfg.CONF.service_credentials.os_region_name,
        'endpoint_type': cfg.CONF.service_credentials.os_endpoint_type,
    }

    # When swiftclient supports session, use session instead of
    # preauthtoken param below
    _swiftclient = swiftclient.client.Connection(
        auth_version='2',
        user=cfg.CONF.service_credentials.username,
        key=cfg.CONF.service_credentials.password,
        authurl=cfg.CONF.service_credentials.auth_url,
        tenant_name=cfg.CONF.service_credentials.tenant_name,
        os_options=os_options,
        cacert=cfg.CONF.service_credentials.cafile,
        insecure=cfg.CONF.service_credentials.insecure
    )

    return _swiftclient


# TODO(lakshmiS) See if we can cache this.
# Cached members will be equal to # of accounts at max.
def get_swiftclient_st(storageurl):
    service_type = 'object-store'
    _get_session()

    os_options = {
        'service_type': service_type,
        'region_name': cfg.CONF.service_credentials.os_region_name,
        'endpoint_type': cfg.CONF.service_credentials.os_endpoint_type,
    }
    swift_client = swiftclient.client.Connection(
        auth_version='2',
        user=cfg.CONF.service_credentials.username,
        key=cfg.CONF.service_credentials.password,
        authurl=cfg.CONF.service_credentials.auth_url,
        tenant_name=cfg.CONF.service_credentials.tenant_name,
        os_options=os_options,
        cacert=cfg.CONF.service_credentials.cafile,
        insecure=cfg.CONF.service_credentials.insecure,
        preauthurl=storageurl,
    )
    return swift_client


def get_keystoneclient():
    session = _get_session()

    return ks_client.Client(
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name)
