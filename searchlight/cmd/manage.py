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

import concurrent.futures
import copy
import signal
import sys
import time

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import encodeutils

from elasticsearch import exceptions as es_exc
from keystoneclient import exceptions
from searchlight.common import config
from searchlight.common import utils
from searchlight.elasticsearch.plugins import utils as es_utils
from searchlight.i18n import _

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

manage_opts = [
    cfg.IntOpt('workers', default=6, min=1,
               help="Maximum number of worker threads for indexing.")
]

CONF.register_opts(manage_opts, group='manage')


# Decorators for actions
def args(*args, **kwargs):
    def _decorator(func):
        func.__dict__.setdefault('args', []).insert(0, (args, kwargs))
        return func
    return _decorator


class IndexCommands(object):
    def __init__(self):
        utils.register_plugin_opts()

    def _plugin_api(self, plugin_obj, index_names):
        """Helper to re-index using the plugin API within a thread, allowing
           all plugins to re-index simultaneously. We may need to cleanup.
           See sig_handler() for more info.
        """
        gname = plugin_obj.resource_group_name
        index_name = index_names[gname]
        dtype = plugin_obj.document_type

        LOG.info("API Reindex start %(type)s into %(index_name)s" %
                 {'type': dtype, 'index_name': index_name})

        try:
            plugin_obj.index_initial_data(index_name=index_name)
            es_utils.refresh_index(index_name)

            LOG.info("API Reindex end %(type)s into %(index_name)s" %
                     {'type': dtype, 'index_name': index_name})
        except exceptions.EndpointNotFound:
            # Display a warning, do not propagate.
            doc = plugin_obj.get_document_type()
            LOG.warning("Service is not available for plugin: "
                        "%(doc)s" % {"doc": doc})
        except Exception as e:
            LOG.exception("Failed to setup index extension "
                          "%(ex)s: %(e)s" % {'ex': index_name, 'e': e})
            raise

    def _es_reindex_worker(self, es_reindex, resource_groups, index_names):
        """Helper to re-index using the ES reindex helper, allowing all ES
           re-indexes to occur simultaneously. We may need to cleanup. See
           sig_handler() for more info.
        """
        for group in index_names.keys():
            # Grab the correct tuple as a list, convert list to a
            # single tuple, extract second member (the search
            # alias) of tuple.
            plugins_reindex = [
                doc_type for doc_type, plugin in es_reindex.items()
                if plugin.resource_group_name == group]
            alias_search = [a for a in resource_groups if a[0] == group][0][1]
            LOG.info("ES Reindex start from %(src)s to %(dst)s "
                     "for types %(types)s" %
                     {'src': alias_search, 'dst': index_names[group],
                      'types': ', '.join(plugins_reindex)})
            dst_index = index_names[group]
            try:
                es_utils.reindex(src_index=alias_search,
                                 dst_index=dst_index,
                                 type_list=plugins_reindex)
                es_utils.refresh_index(dst_index)
                LOG.info("ES Reindex end from %(src)s to %(dst)s "
                         "for types %(types)s" %
                         {'src': alias_search, 'dst': index_names[group],
                          'types': ', '.join(plugins_reindex)})
            except Exception as e:
                LOG.exception("Failed to setup index extension "
                              "%(ex)s: %(e)s" % {'ex': dst_index, 'e': e})
                raise

    @args('--group', metavar='<group>', dest='group',
          help='Index only this Resource Group (or a comma separated list)')
    @args('--type', metavar='<type>', dest='_type',
          help='Index only this type (or a comma separated list)')
    @args('--force', dest='force', action='store_true',
          help="Don't prompt (answer 'y')")
    @args('--apply-mapping-changes', dest='force_es', action='store_true',
          help="Use existing indexed data but apply mappings and settings")
    @args('--notification-less', dest='notification_less', action='store_true',
          help="Index only plugins without notification")
    def sync(self, group=None, _type=None, force=False, force_es=False,
             notification_less=False):
        def wait_for_threads():
            """Patiently wait for all running threads to complete. Returns true
            if everything finished successfully, false on cancellation or error
            """
            threads_running = True
            while threads_running:

                # Are any threads still running?
                threads_running = False
                for name, future in futures:
                    if not future.done():
                        threads_running = True
                        break

                time.sleep(1)

            # If they're all done, did they all complete successfully?
            unsuccessful = []
            for name, future in futures:
                if future.cancelled() or future.exception(timeout=0):
                    unsuccessful.append(name)

            if unsuccessful:
                LOG.error("The following indexing threads did not complete "
                          "successfully, due to error or cancellation: %s",
                          ", ".join(unsuccessful))
                return False
            return True

        # Signal handler to catch interrupts from the user (ctl-c)
        def sig_handler(signum, frame):
            """When rudely interrupted by the user, we will want to clean up
               after ourselves. We have potentially three pieces of unfinished
               business.
                   1. We have running threads. Cancel them.
                   2. Wait for all threads to finish.
                   3. We created new indices in Elasticsearch. Remove them.
            """
            # Cancel any and all threads.
            LOG.error("Cancelling running threads")
            for name, future in futures:
                # At this point, because the futures have been cancelled,
                # they'll break out of the wait loop with an error state.
                LOG.info("Cancelling '%s' thread", name)
                future.cancel()

        if _type and notification_less:
            LOG.error("Ignoring --type since --notification-less is "
                      "specified.")

        if force_es and (_type or notification_less):
            if notification_less:
                option = "--notification-less"
            else:
                option = "--type"
            # The user cannot specify both of these options simultaneously.
            print("\nInvalid set of options.")
            print("Cannot specify both '%s' and '--apply-mapping-changes' "
                  "simultaneously.\n" % option)
            sys.exit(1)

        try:
            max_workers = cfg.CONF.manage.workers
        except cfg.ConfigFileValueError:
            LOG.error("Invalid value for config file option "
                      "'manage.workers'. The number of thread workers "
                      "must be greater than 0.")
            sys.exit(3)

        # Grab the list of plugins registered as entry points through stevedore
        search_plugins = utils.get_search_plugins()

        # Verify all indices and types have registered plugins.
        # index and _type are lists because of nargs='*'
        group = group.split(',') if group else []
        _type = _type.split(',') if _type else []

        _plugins_without_notification = []

        _type = utils.expand_type_matches(
            _type, search_plugins.keys())
        LOG.debug("After expansion, 'type' argument: %s", ", ".join(_type))

        group_set = set(group)
        type_set = set(_type)

        """
        The caller can specify a sync based on either the Document Type or the
        Resource Group. With the Zero Downtime functionality, we are using
        aliases to index into ElasticSearch. We now have multiple Document
        Types sharing a single alias. If any member of a Resource Group (an
        ES alias) is re-syncing *all* members of that Resource Group needs
        to re-sync.

        The final list of plugins to use for re-syncing *must* come only from
        the Resource Group specifications. The "type" list is used only to make
        the "group" list complete. We need a two pass algorithm for this.

        First pass: Analyze the plugins according to the "type" list. This
          turns a type in the "type" list to a group in the "group" list.

        Second pass: Analyze the plugins according to the "group" list. Create
          the plugin list that will be used for re-syncing.

        Note: We cannot call any plugin's sync() during these two passes. The
        sync needs to be a separate step. The API states that if any invalid
        plugin was specified by the caller, the entire operation fails.
        """
        if notification_less:
            for res_type, ext in search_plugins.items():
                if not ext.obj.get_notification_handler():
                    _plugins_without_notification.append(
                        ext.obj.get_document_type())
            # Override _type list.
            _type = _plugins_without_notification

        # First Pass: Document Types.
        if _type:
            for res_type, ext in search_plugins.items():
                plugin_obj = ext.obj
                type_set.discard(plugin_obj.get_document_type())
                if plugin_obj.get_document_type() in _type:
                    group.append(plugin_obj.resource_group_name)

        # Second Pass: Resource Groups (including those from types).
        # This pass is a little tricky. If "group" is empty, it implies every
        # resource gets re-synced. The command group_set.discard() is a no-op
        # when "group" is empty.
        resource_groups = []
        plugin_objs = {}
        plugins_list = []
        for res_type, ext in search_plugins.items():
            plugin_obj = ext.obj
            group_set.discard(plugin_obj.resource_group_name)
            if (not group) or (plugin_obj.resource_group_name in group):
                plugins_list.append((res_type, ext))
                plugin_objs[plugin_obj.resource_group_name] = plugin_obj
                if not (plugin_obj.resource_group_name,
                        plugin_obj.alias_name_search,
                        plugin_obj.alias_name_listener) in resource_groups:
                    resource_groups.append((plugin_obj.resource_group_name,
                                            plugin_obj.alias_name_search,
                                            plugin_obj.alias_name_listener))

        if group_set or type_set:
            print("Some index names or types do not have plugins "
                  "registered. Index names: %s. Types: %s" %
                  (",".join(group_set) or "<None>",
                   ",".join(type_set) or "<None>"))
            print("Aborting.")
            sys.exit(1)

        # As an optimization, if any types are explicitly requested, we
        # will index them from their service APIs. The rest will be
        # indexed from an existing ES index, if one exists.
        #
        # Also, if force_es is set the user wishes to use ES exclusively
        # as the source for all data. This implies everything in the
        # es_reindex dictionary and nothing in the plugins_to_index list.
        es_reindex = {}
        es_reindex_mapping = {}
        plugins_to_index = copy.copy(plugins_list)
        if _type or force_es:
            for resource_type, ext in plugins_list:
                doc_type = ext.obj.get_document_type()

                # If force_es is set, then "_type" is None. Always do this.
                # If force_es is None, then "_type" is set. Adjust as needed.
                if doc_type not in _type:
                    es_reindex[doc_type] = ext.obj
                    doc_type_list = es_reindex_mapping.setdefault(
                        ext.obj.alias_name_search, [])
                    doc_type_list.append(doc_type)
                    # Don't reindex this type
                    plugins_to_index.remove((resource_type, ext))

        missing_index, missing_type = \
            es_utils.find_missing_types(es_reindex_mapping)

        if missing_index:
            print(
                "Missing indices when trying to re-index resource information"
                " from existing Elasticsearch data: %(index)s.\n" % {
                    "index": ", ".join(missing_index)})

        if missing_type:
            print(
                "Missing type mappings when trying to re-index resource "
                "information from existing Elasticsearch data: %(type)s.\n" % {
                    "type": ", ".join(missing_type)})

        if not force and (missing_index or missing_type):
            print(
                "Either indices or type mappings are missing, you should do "
                "a full api re-index without specifying --type parameter.\n"
            )
            print("Aborting")
            sys.exit(1)

        if not force:
            # For display purpose, we want to iterate on only parthenogenetic
            # plugins that are not the children of another plugin. If there
            # are children plugins they will be displayed when we call
            # get_index_display_name(). Therefore any child plugins in the
            # display list, will be listed twice.
            display_plugins = []
            plugins_without_notifications = []
            for res, ext in plugins_list:
                if not ext.obj.parent_plugin:
                    display_plugins.append((res, ext))

            def format_selection(selection):
                def _format_plugin(plugin, indent=0):
                    plugin_doc_type = plugin.get_document_type()
                    handler = plugin.get_notification_handler()

                    display = '\n' + '    ' * indent + '--> ' if indent else ''
                    display += '%s (%s)' % (plugin_doc_type,
                                            plugin.resource_group_name)
                    if plugin_doc_type in es_reindex:
                        display += ' *'
                    if not handler:
                        display += ' !!'
                        plugins_without_notifications.append(plugin)
                    return display + ''.join(_format_plugin(c, indent + 1)
                                             for c in plugin.child_plugins)

                return _format_plugin(selection[1].obj)

            all_res_groups = set(grp[0] for grp in resource_groups)
            print("\nResources in these groups must be re-indexed: %s." %
                  ", ".join(all_res_groups))

            print("Resource types (and aliases) matching selection:\n\n%s\n" %
                  '\n'.join(map(format_selection, sorted(display_plugins))))

            if es_reindex:
                msg = ("Any types marked with * will be reindexed from "
                       "existing Elasticsearch data.\n")
                if notification_less:
                    LOG.warning(msg)
                else:
                    print(msg)

            if plugins_without_notifications:
                print("Any types marked with !! do not support incremental "
                      "updates via the listener.")
                print("These types must be fully re-indexed periodically or "
                      "should be disabled.\n")

            if not notification_less:
                ans = input(
                    "\nUse '--force' to suppress this message.\n"
                    "OK to continue? [y/n]: ")
                if ans.lower() != 'y':
                    print("Aborting.")
                    sys.exit(0)

        # Start the re-indexing process.
        # Now we are starting to change Elasticsearch. Let's clean up
        # if interrupted. Set index_names/futures here for cleaner code
        # in the signal handler.
        index_names = {}
        # futures will contain tuples (name, future)
        futures = []
        signal.signal(signal.SIGINT, sig_handler)

        # Step #1: Create new indexes for each Resource Group Type.
        #   The index needs to be fully functional before it gets
        #   added to any aliases. This includes all settings and
        #   mappings. Only then can we add it to the aliases. We first
        #   need to create all indexes. This is done by resource group.
        #   We cache and turn off new indexes' refresh intervals,
        #   this will improve the performance of data re-syncing.
        #   After data get re-synced, set the refresh interval back.
        #   Once all indexes are created, we need to initialize the
        #   indexes. This is done by document type.
        #   NB: The aliases remain unchanged for this step.
        refresh_intervals = {}
        try:
            for group, search, listen in resource_groups:
                index_name = es_utils.create_new_index(group)
                index_names[group] = index_name

                refresh_intervals[index_name] = \
                    es_utils.get_index_refresh_interval(index_name)
                # Disable refresh interval by setting its value to -1
                es_utils.set_index_refresh_interval(index_name, -1)
            for resource_type, ext in plugins_list:
                plugin_obj = ext.obj
                group_name = plugin_obj.resource_group_name
                plugin_obj.prepare_index(
                    index_name=index_names[group_name])
        except Exception:
            LOG.error("Error creating index or mapping, aborting "
                      "without indexing")
            es_utils.alias_error_cleanup(index_names)
            raise

        # Step #2: Modify new index to play well with multiple indices.
        #   There is a "feature" of Elasticsearch where some types of
        #   queries do not work across multiple indices if there are no
        #   mappings for the specified document types. This is an issue we
        #   run into with our RBAC functionality. We need to modify the new
        #   index to work for these cases. We will grab all document types
        #   from the plugins and add a mapping for them as needed to the newly
        #   created indices.
        doc_type_info = []
        for res_type, ext in search_plugins.items():
            doc_type_info.append((ext.obj.get_document_type(),
                                  ext.obj.parent_plugin_type))
        for index in list(index_names.values()):
            es_utils.add_extra_mappings(index_name=index,
                                        doc_type_info=doc_type_info)

        # Step #3: Set up the aliases for all Resource Type Group.
        #   These actions need to happen outside of the plugins. Now that
        #   the indexes are created and fully functional we can associate
        #   them with the aliases.
        #   NB: The indexes remain unchanged for this step.
        for group, search, listen in resource_groups:
            try:
                es_utils.setup_alias(index_names[group], search, listen)
            except Exception as e:
                LOG.exception("Failed to setup alias for resource group "
                              "%(g)s: %(e)s" % {'g': group, 'e': e})
                es_utils.alias_error_cleanup(index_names)
                raise

        # Step #4: Re-index all resource types in this Resource Type Group.
        #   NB: The "search" and "listener" aliases remain unchanged for this
        #       step.
        #   NB: We will be spinning off this working into separate threads.
        #       We will limit each thread to a single resource type. For
        #       more information, please refer to the spec:
        #           searchlight-specs/specs/newton/
        #             index-performance-enhancement.rst
        ThreadPoolExec = concurrent.futures.ThreadPoolExecutor
        with ThreadPoolExec(max_workers=max_workers) as executor:
            try:
                futures = []
                # Start threads for plugin API.
                for res, ext in plugins_to_index:
                    # Throw the plugin into the thread pool.
                    plugin_obj = ext.obj
                    futures.append((res, executor.submit(self._plugin_api,
                                   plugin_obj, index_names)))

                # Start the single thread for ES re-index.
                if es_reindex:
                    futures.append(
                        ('elasticsearch-reindex',
                         executor.submit(self._es_reindex_worker, es_reindex,
                                         resource_groups, index_names))
                    )

                # Sit back, relax and wait for the threads to complete.
                finished_successfully = wait_for_threads()

                if not finished_successfully:
                    if index_names:
                        es_utils.alias_error_cleanup(index_names)
                    LOG.error("Rolled back; exiting")
                    sys.exit(1)

            except Exception:
                # An exception occurred. Start cleaning up ElasticSearch and
                # inform the user.
                es_utils.alias_error_cleanup(index_names)
                raise

        # Step #5: Update the "search" alias.
        #   All re-indexing has occurred. The index/alias is the same for
        #   all resource types within this Resource Group. These actions need
        #   to happen outside of the plugins. Also restore refresh interval
        #   for indexes, this will make data in the indexes become searchable.
        #   NB: The "listener" alias remains unchanged for this step.
        for index_name, interval in refresh_intervals.items():
            es_utils.set_index_refresh_interval(index_name, interval)

        old_index = {}
        for group, search, listen in resource_groups:
            old_index[group] = \
                es_utils.alias_search_update(search, index_names[group])

        # Step #6: Update the "listener" alias.
        #   The "search" alias has been updated. This involves both removing
        #   the old index from the alias as well as deleting the old index.
        #   These actions need to happen outside of the plugins.
        #   NB: The "search" alias remains unchanged for this step.
        for group, search, listen in resource_groups:
            try:
                # If any exception raises, ignore and continue to delete
                # any other old indexes.
                es_utils.delete_index(old_index[group])
            except Exception as e:
                LOG.error(encodeutils.exception_to_unicode(e))

    def aliases(self):
        # Grab a list of aliases used by Searchlight.
        aliases = []
        for res_type, ext in utils.get_search_plugins().items():
            aliases.append(ext.obj.alias_name_listener)
            aliases.append(ext.obj.alias_name_search)

        # Grab the indices associated with the aliases. The end result is
        # a dictionary where the key is the index and the value is a list
        # of aliases associated with that index.
        indices = {}
        for alias in set(aliases):
            try:
                response = es_utils.get_indices(alias)
            except es_exc.NotFoundError:
                # Ignore and continue.
                response = {}
            except Exception as e:
                # Probably an ES connection issue. Alert the user.
                LOG.error("Failed retrieving indices from Elasticsearch "
                          "%(a)s %(e)s" % {'a': alias, 'e': e})
                sys.exit(3)

            for index in response.keys():
                if index not in indices:
                    indices[index] = [alias]
                else:
                    indices[index].append(alias)

        if not indices:
            print("\nNo Elasticsearch indices for Searchlight exist.")
        else:
            print("\nList of Elasticsearch indices (and their associated"
                  " aliases) used by Searchlight.\n")
            print("The indices are based on the config file.")
            print("To view indices used by other Searchlight config "
                  "files, use the --config-file option.\n")
            print("Indices are denoted with a '*'")
            print("Aliases are denoted with a '+'\n")
            for index in indices:
                print("    * " + index)
                for alias in indices[index]:
                    print("        + " + alias)
        print("\n")


def add_command_parsers(subparsers):
    """Adds any commands and subparsers for their actions. This code's
    from the Glance equivalent.
    """
    for command_name, cls in COMMANDS.items():
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
    'index': IndexCommands,
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
                                          prog='searchlight')
        config.parse_args(default_config_files=cfg_files)
        config.set_config_defaults()
        logging.setup(CONF, 'searchlight')

        func_kwargs = {}
        for k in CONF.command.action_kwargs:
            v = getattr(CONF.command, 'action_kwarg_' + k)
            if v is None:
                continue
            if isinstance(v, str):
                v = encodeutils.safe_decode(v)
            func_kwargs[k] = v
        func_args = [encodeutils.safe_decode(arg)
                     for arg in CONF.command.action_args]
        return CONF.command.action_fn(*func_args, **func_kwargs)

    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)


if __name__ == '__main__':
    main()
