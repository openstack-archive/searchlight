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
from distutils.version import LooseVersion
import os

from cinderclient import client as cinder_client
from designateclient.v2 import client as designate_client
from glanceclient import client as glance_client
from ironicclient import client as ironic_client
from ironicclient import exc as ironic_exceptions
from keystoneauth1 import loading as ka_loading
from keystoneclient import exceptions as keystone_exceptions

import keystoneclient.v3.client as ks_client
import neutronclient.v2_0.client as neutron_client
from novaclient import client as nova_client
import swiftclient

from searchlight.common import exception

from oslo_config import cfg


client_opts = [
    cfg.StrOpt('os-region-name',
               default=os.environ.get('OS_REGION_NAME'),
               help='Region name to use for OpenStack service endpoints.'
                    'If set, will be included in plugin mappings.'),
    cfg.StrOpt('os-endpoint-type',
               default=os.environ.get('OS_ENDPOINT_TYPE', 'publicURL'),
               help='Type of endpoint in Identity service catalog to '
                    'use for communication with OpenStack services.'),
]

compute_api_version = cfg.StrOpt(
    'compute_api_version',
    default='2.1',
    help='The compute API (micro)version, the provided '
         'compute API (micro)version should be not smaller '
         'than 2.1 and not larger than the max supported '
         'Compute API microversion. The current supported '
         'Compute API versions can be checked using: '
         'nova version-list.')

GROUP = "service_credentials"
CONF = cfg.CONF

CONF.register_opts(client_opts, group=GROUP)
CONF.register_opt(compute_api_version, group="service_credentials:nova")

ka_loading.register_session_conf_options(CONF, GROUP)
ka_loading.register_auth_conf_options(CONF, GROUP)

_session = None

NOVA_MIN_API_VERSION = '2.1'
IRONIC_API_VERSION = '1.22'


def _get_session():
    global _session
    if not _session:
        auth = ka_loading.load_auth_from_conf_options(CONF, GROUP)
        _session = ka_loading.load_session_from_conf_options(
            CONF, GROUP, auth=auth)
    return _session


def get_glanceclient():
    session = _get_session()

    return glance_client.Client(
        version='2',
        session=session,
        interface=CONF.service_credentials.os_endpoint_type,
        region_name=CONF.service_credentials.os_region_name
    )


def get_novaclient():

    def do_get_client(api_version=2.1):
        session = _get_session()
        return nova_client.Client(
            version=api_version,
            session=session,
            region_name=CONF.service_credentials.os_region_name,
            endpoint_type=CONF.service_credentials.os_endpoint_type
        )

    version = CONF["service_credentials:nova"].compute_api_version
    # Check whether Nova can support the provided microversion.
    max_version = do_get_client().versions.list()[-1].version
    if LooseVersion(version) > LooseVersion(max_version) or \
            LooseVersion(version) < LooseVersion(NOVA_MIN_API_VERSION):
        raise exception.InvalidAPIVersionProvided(
            service='compute service', min_version=NOVA_MIN_API_VERSION,
            max_version=max_version)

    return do_get_client(version)


def get_designateclient():
    session = _get_session()

    return designate_client.Client(
        session=session,
        region_name=CONF.service_credentials.os_region_name,
        endpoint_type=CONF.service_credentials.os_endpoint_type
    )


def get_neutronclient():
    session = _get_session()
    return neutron_client.Client(
        session=session,
        region_name=CONF.service_credentials.os_region_name,
        endpoint_type=CONF.service_credentials.os_endpoint_type
    )


def get_cinderclient():
    session = _get_session()

    return cinder_client.Client(
        version='2',
        session=session,
        region_name=CONF.service_credentials.os_region_name,
        endpoint_type=CONF.service_credentials.os_endpoint_type
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
        'region_name': CONF.service_credentials.os_region_name,
        'endpoint_type': CONF.service_credentials.os_endpoint_type,
    }

    # When swiftclient supports session, use session instead of
    # preauthtoken param below
    _swiftclient = swiftclient.client.Connection(
        auth_version='2',
        user=CONF.service_credentials.username,
        key=CONF.service_credentials.password,
        authurl=CONF.service_credentials.auth_url,
        tenant_name=CONF.service_credentials.tenant_name,
        os_options=os_options,
        cacert=CONF.service_credentials.cafile,
        insecure=CONF.service_credentials.insecure
    )

    return _swiftclient


# TODO(lakshmiS) See if we can cache this.
# Cached members will be equal to # of accounts at max.
def get_swiftclient_st(storageurl):
    service_type = 'object-store'
    _get_session()

    os_options = {
        'service_type': service_type,
        'region_name': CONF.service_credentials.os_region_name,
        'endpoint_type': CONF.service_credentials.os_endpoint_type,
    }
    swift_client = swiftclient.client.Connection(
        auth_version='2',
        user=CONF.service_credentials.username,
        key=CONF.service_credentials.password,
        authurl=CONF.service_credentials.auth_url,
        tenant_name=CONF.service_credentials.tenant_name,
        os_options=os_options,
        cacert=CONF.service_credentials.cafile,
        insecure=CONF.service_credentials.insecure,
        preauthurl=storageurl,
    )
    return swift_client


def get_keystoneclient():
    session = _get_session()

    return ks_client.Client(
        session=session,
        region_name=CONF.service_credentials.os_region_name)


def get_ironicclient():
    session = _get_session()
    try:
        return ironic_client.get_client(
            '1',
            session=session,
            os_region_name=CONF.service_credentials.os_region_name,
            os_endpoint_type=CONF.service_credentials.os_endpoint_type,
            os_ironic_api_version=IRONIC_API_VERSION
        )
    except ironic_exceptions.AmbiguousAuthSystem:
        raise keystone_exceptions.EndpointNotFound()
