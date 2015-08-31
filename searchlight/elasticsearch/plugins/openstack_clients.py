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

from designateclient.v2 import client as designateclient
from glanceclient import exc as glance_exc
from glanceclient.v2 import client as glance
from keystoneclient import auth as ks_auth
from keystoneclient import session as ks_session
import novaclient.client
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


# Glance still needs special handling because versions prior to 1.0 don't
# support keystone sessions. Rather than maintain two codepaths, we'll do this
_glanceclient = None


def clear_cached_glanceclient_on_unauthorized(fn):
    def wrapper(*args, **kwargs):
        global _session
        global _glanceclient
        try:
            return fn(*args, **kwargs)
        except glance_exc.Unauthorized:
            _session = None
            _glanceclient = None
            return fn(*args, **kwargs)
    return wrapper


def get_glanceclient():
    global _glanceclient
    if _glanceclient:
        return _glanceclient

    session = _get_session()

    endpoint = session.get_endpoint(
        service_type='image',
        region_name=cfg.CONF.service_credentials.os_region_name,
        interface=cfg.CONF.service_credentials.os_endpoint_type)

    _glanceclient = glance.Client(
        endpoint=endpoint,
        token=session.auth.get_token(session),
        cacert=cfg.CONF.service_credentials.cafile,
        insecure=cfg.CONF.service_credentials.insecure
    )
    return _glanceclient

    # Once we use 1.0, use the below code.
    # session = _get_session()

    # return glance.Client(
    #     session=session
    # )


def get_novaclient():
    session = _get_session()

    return novaclient.client.Client(
        version=2,
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name)


def get_designateclient():
    session = _get_session()

    return designateclient.Client(
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name,
    )
