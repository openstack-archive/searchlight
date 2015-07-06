# Copyright 2015 Intel Corporation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import six
import sys

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils

from searchlight.common import config
from searchlight.common import utils
from searchlight.elasticsearch.plugins import openstack_clients
from searchlight import i18n


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE


class IndexCommands(object):
    def __init__(self):
        pass

    def sync(self):
        for ext in utils.get_search_plugins():
            try:
                ext.obj.setup()
            except Exception as e:
                LOG.error(_LE("Failed to setup index extension "
                              "%(ext)s: %(e)s") % {'ext': ext.name,
                                                   'e': e})


def add_command_parsers(subparsers):
    """Adds any commands and subparsers for their actions. This code's
    from the Glance equivalent.
    """
    for category_name, cls in six.iteritems(CATEGORIES):
        command_object = cls()

        parser = subparsers.add_parser(category_name)
        parser.set_defaults(command_object=command_object)

        category_subparsers = parser.add_subparsers(dest='action')

        for (action, action_fn) in methods_of(command_object):
            parser = category_subparsers.add_parser(action)

            action_kwargs = []
            for args, kwargs in getattr(action_fn, 'args', []):
                action_kwargs.append(kwargs['dest'])
                kwargs['dest'] = 'action_kwarg_' + kwargs['dest']

                parser.add_argument(*args, **kwargs)

            parser = category_subparsers.add_parser(action)

            parser.set_defaults(action_fn=action_fn)
            parser.set_defaults(action_kwargs=action_kwargs)

            parser.add_argument('action_args', nargs='*')


command_opt = cfg.SubCommandOpt('command',
                                title='Commands',
                                help='Available commands',
                                handler=add_command_parsers)


CATEGORIES = {
    'index': IndexCommands
}


def methods_of(obj):
    """Get all callable methods of an object that don't start with underscore

    returns a list of tuples of the form (method_name, method)
    """
    result = []
    for i in dir(obj):
        if callable(getattr(obj, i)) and not i.startswith('_'):
            result.append((i, getattr(obj, i)))
    return result


def main():
    CONF.register_cli_opt(command_opt)
    if len(sys.argv) < 2:
        script_name = sys.argv[0]
        print("%s category action [<args>]" % script_name)
        print(_("Available categories:"))
        for category in CATEGORIES:
            print(_("\t%s") % category)
        sys.exit(2)

    try:
        logging.register_options(CONF)
        openstack_clients.register_cli_opts()

        cfg_files = cfg.find_config_files(project='searchlight',
                                          prog='searchlight-api')
        config.parse_args(default_config_files=cfg_files)
        logging.setup(CONF, 'searchlight')

        func_kwargs = {}
        for k in CONF.command.action_kwargs:
            v = getattr(CONF.command, 'action_kwarg_' + k)
            if v is None:
                continue
            if isinstance(v, six.string_types):
                v = encodeutils.safe_decode(v)
            func_kwargs[k] = v
        func_args = [encodeutils.safe_decode(arg)
                     for arg in CONF.command.action_args]
        return CONF.command.action_fn(*func_args, **func_kwargs)

    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)
