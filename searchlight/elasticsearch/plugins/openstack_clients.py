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


def get_glanceclient():
    session = _get_session()

    return glance.Client(
        session=session,
        region_name=cfg.CONF.service_credentials.os_region_name
    )


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
