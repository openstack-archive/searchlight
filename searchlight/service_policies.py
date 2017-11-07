# Copyright (c) 2016 Hewlett-Packard Enterprise Development L.P.
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

import logging
import os

from oslo_config import cfg
from oslo_policy import policy

from searchlight.common import policies


LOG = logging.getLogger(__name__)


policy_file_opts = [
    cfg.StrOpt("service_policy_path",
               default='',
               help="Base path for policy files. If not specified, "
                    "oslo.config search paths will be used"),
    cfg.DictOpt("service_policy_files",
                default={},
                help="Service policy files of the form <service type>:<path>,"
                     "<service_type>:<path>. Service type should be e.g."
                     "'compute', 'volume'")
]
cfg.CONF.register_opts(policy_file_opts, group="service_policies")


_ENFORCERS = None


class MissingPolicyFile(Exception):
    pass


def _get_enforcers():
    global _ENFORCERS
    if not _ENFORCERS:
        _ENFORCERS = {}
        pol_files = cfg.CONF.service_policies.service_policy_files
        for service, pol_file in pol_files.items():
            base_path = str(cfg.CONF.service_policies.service_policy_path)
            service_policy_path = os.path.join(base_path,
                                               pol_file)
            enforcer = policy.Enforcer(cfg.CONF, service_policy_path)
            missing_config_file = False

            # oslo.policy's approach to locating these files seems to be
            # changing; current master doesn't raise an exception
            try:
                enforcer.load_rules()
                enforcer.register_defaults(policies.list_rules())
                if not enforcer.policy_path:
                    missing_config_file = True
            except cfg.ConfigFilesNotFoundError:
                missing_config_file = True

            if missing_config_file:
                LOG.error("Policy file for service %(service)s not found"
                          " in %(policy_file)s (base path %(base)s)" %
                          {"service": service, "policy_file": pol_file,
                           "base": service_policy_path})
                raise MissingPolicyFile(
                    "Could not find policy file %(pol_file)s for service "
                    "type %(service)s" % {'pol_file': pol_file,
                                          'service': service})

            LOG.debug("Adding policy enforcer for %s" % service)
            _ENFORCERS[service] = enforcer

    return _ENFORCERS


def _reset_enforcers():
    global _ENFORCERS
    _ENFORCERS = None


def check_policy_files():
    """Verifies that any configured policy files exist and are valid"""
    _get_enforcers()


def get_enforcer_for_service(service_type):
    enforcers = _get_enforcers()
    if service_type in enforcers:
        return enforcers[service_type]

    LOG.debug("No policy file configured for %s", service_type)
    return None
