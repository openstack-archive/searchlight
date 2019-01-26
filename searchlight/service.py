#!/usr/bin/env python
#
# Copyright 2012-2014 eNovance <licensing@enovance.com>
# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

import sys

from oslo_config import cfg
import oslo_i18n
from oslo_log import log
import oslo_messaging
from oslo_reports import guru_meditation_report as gmr

from searchlight.common import utils
from searchlight import version

CONF = cfg.CONF

LOG = log.getLogger(__name__)
_DEFAULT_LOG_LEVELS = ['keystonemiddleware=WARN', 'stevedore=WARN']


class WorkerException(Exception):
    """Exception for errors relating to service workers."""


def prepare_service(argv=None):
    oslo_i18n.enable_lazy()
    log.set_defaults(_DEFAULT_LOG_LEVELS)
    log.register_options(CONF)
    gmr.TextGuruMeditation.setup_autorun(version)
    utils.register_plugin_opts()

    if argv is None:
        argv = sys.argv
    CONF(argv[1:], project='searchlight')
    log.setup(cfg.CONF, 'searchlight')
    oslo_messaging.set_transport_defaults('searchlight')
