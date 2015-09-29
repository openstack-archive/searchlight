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
from searchlight import i18n


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
_ = i18n._
_LE = i18n._LE
_LI = i18n._LI


# Decorators for actions
def args(*args, **kwargs):
    def _decorator(func):
        func.__dict__.setdefault('args', []).insert(0, (args, kwargs))
        return func
    return _decorator


class IndexCommands(object):
    def __init__(self):
        pass

    @args('--index', metavar='<index>', dest='index',
          help='Index only this index (or a comma separated list)')
    @args('--type', metavar='<type>', dest='_type',
          help='Index only this type (or a comma seperated list)')
    @args('--force', dest='force', action='store_true',
          help="Don't prompt (answer 'y')")
    def sync(self, index=None, _type=None, force=False):
        # Verify all indices and types have registered plugins.
        # index and _type are lists because of nargs='*'
        index = index.split(',') if index else []
        _type = _type.split(',') if _type else []

        indices_set = set(index)
        types_set = set(_type)

        plugins_to_index = []
        for resource_type, ext in six.iteritems(utils.get_search_plugins()):
            plugin_obj = ext.obj
            indices_set.discard(plugin_obj.get_index_name())
            types_set.discard(plugin_obj.get_document_type())

            skip = (index and plugin_obj.get_index_name() not in index or
                    _type and plugin_obj.get_document_type() not in _type)
            if not skip:
                plugins_to_index.append((resource_type, ext))

        if indices_set or types_set:
            print("Some index names or types do not have plugins "
                  "registered. Index names: %s. Types: %s" %
                  (",".join(indices_set) or "<None>",
                   ",".join(types_set) or "<None>"))
            print("Aborting.")
            sys.exit(1)

        if not force:
            def format_selection(selection):
                resource_type, ext = selection
                return '  %s (%s)' % (ext.obj.get_document_type(),
                                      ext.obj.get_index_name())

            print("\nResource types (and indices) matching selection:\n%s\n" %
                  '\n'.join(map(format_selection, plugins_to_index)))

            ans = raw_input(
                "Indexing will delete existing data and mapping(s) before "
                "reindexing.\nUse '--force' to suppress this "
                "message.\nOK to continue? [y/n]: ")
            if ans.lower() != 'y':
                print("Aborting.")
                sys.exit(0)

        for resource_type, ext in plugins_to_index:
            plugin_obj = ext.obj
            try:
                plugin_obj.initial_indexing(clear=True)
            except Exception as e:
                LOG.error(_LE("Failed to setup index extension "
                              "%(ext)s: %(e)s") % {'ext': ext.name,
                                                   'e': e})


def add_command_parsers(subparsers):
    """Adds any commands and subparsers for their actions. This code's
    from the Glance equivalent.
    """
    for command_name, cls in six.iteritems(COMMANDS):
        command_object = cls()

        parser = subparsers.add_parser(command_name)
        parser.set_defaults(command_object=command_object)

        command_subparsers = parser.add_subparsers(dest='action')

        for (action, action_fn) in methods_of(command_object):
            parser = command_subparsers.add_parser(action)

            action_kwargs = []
            for args, kwargs in getattr(action_fn, 'args', []):
                if kwargs['dest'].startswith('action_kwarg_'):
                    action_kwargs.append(
                        kwargs['dest'][len('action_kwarg_'):])
                else:
                    action_kwargs.append(kwargs['dest'])
                    kwargs['dest'] = 'action_kwarg_' + kwargs['dest']

                parser.add_argument(*args, **kwargs)

            parser.set_defaults(action_fn=action_fn)
            parser.set_defaults(action_kwargs=action_kwargs)

            parser.add_argument('action_args', nargs='*')


command_opt = cfg.SubCommandOpt('command',
                                title='Commands',
                                help='Available commands',
                                handler=add_command_parsers)


COMMANDS = {
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
        print("%s command action [<args>]" % script_name)
        print(_("Available commands:"))
        for command in COMMANDS:
            print(_("\t%s") % command)
        sys.exit(2)

    try:
        logging.register_options(CONF)

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


if __name__ == '__main__':
    main()
