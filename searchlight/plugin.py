# Copyright 2012 Bouvet ASA
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
import abc

from oslo_config import cfg
from oslo_log import log as logging
from stevedore import extension


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Plugin(object, metaclass=abc.ABCMeta):
    """This class exists as a point for plugins to define
    config options.
    """
    def __init__(self):
        self.name = self.get_config_group_name()
        LOG.debug("Loaded plugin %s" % self.name)

    @classmethod
    def get_cfg_opts(cls):
        group = cfg.OptGroup(cls.get_config_group_name())
        opts = cls.get_plugin_opts()
        return [(group, opts)]

    @classmethod
    def get_config_group_name(cls):
        raise NotImplementedError()

    @classmethod
    def register_cfg_opts(cls, namespace):
        mgr = extension.ExtensionManager(namespace)

        for e in mgr:
            for group, opts in e.plugin.get_cfg_opts():
                if isinstance(group, str):
                    group = cfg.OptGroup(name=group)

                CONF.register_group(group)
                CONF.register_opts(opts, group=group)
