# Copyright 2011 OpenStack Foundation
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

"""
Base test class for running non-stubbed tests (functional tests)

The FunctionalTest class contains helper methods for starting the API
server, grabbing the logs of each, cleaning up pidfiles,
and spinning down the servers.
"""

import atexit
import datetime
import elasticsearch
import importlib
import logging as std_logging
import os
import platform
import requests
import shutil
import signal
import socket
import sys
import tempfile
import time
from unittest import mock
import urllib

import fixtures
from oslo_log import log as logging
from oslo_serialization import jsonutils
import testtools

from searchlight.common import utils
from searchlight.elasticsearch.plugins import utils as es_utils
from searchlight.tests import utils as test_utils


LOG = logging.getLogger(__name__)
tracer = std_logging.getLogger('elasticsearch.trace')
tracer.setLevel(std_logging.INFO)
tracer.addHandler(std_logging.NullHandler())

execute, get_unused_port = test_utils.execute, test_utils.get_unused_port
tracecmd_osmap = {'Linux': 'strace', 'FreeBSD': 'truss'}


class Server(object):
    """
    Class used to easily manage starting and stopping
    a server during functional test runs.
    """
    def __init__(self, test_dir, port, sock=None):
        """
        Creates a new Server object.

        :param test_dir: The directory where all test stuff is kept. This is
                         passed from the FunctionalTestCase.
        :param port: The port to start a server up on.
        """
        self.debug = True
        self.no_venv = False
        self.test_dir = test_dir
        self.bind_port = port
        self.conf_file_name = None
        self.conf_base = None
        self.paste_conf_base = None
        self.exec_env = None
        self.deployment_flavor = ''
        self.property_protection_file = ''
        self.log_file = None
        self.sock = sock
        self.fork_socket = True
        self.process_pid = None
        self.server_module = None
        self.stop_kill = False
        self.elasticsearch_pid = None

    def write_conf(self, **kwargs):
        """
        Writes the configuration file for the server to its intended
        destination.  Returns the name of the configuration file and
        the over-ridden config content (may be useful for populating
        error messages).
        """
        if not self.conf_base:
            raise RuntimeError("Subclass did not populate config_base!")

        conf_override = self.__dict__.copy()
        if kwargs:
            conf_override.update(**kwargs)

        # A config file and paste.ini to use just for this test...we don't want
        # to trample on currently-running Searchlight servers, now do we?

        conf_dir = os.path.join(self.test_dir, 'etc')
        conf_filepath = os.path.join(conf_dir, "%s.conf" % self.server_name)
        if os.path.exists(conf_filepath):
            os.unlink(conf_filepath)
        paste_conf_filepath = conf_filepath.replace(".conf", "-paste.ini")
        if os.path.exists(paste_conf_filepath):
            os.unlink(paste_conf_filepath)
        utils.safe_mkdirs(conf_dir)

        def override_conf(filepath, overridden):
            with open(filepath, 'w') as conf_file:
                conf_file.write(overridden)
                conf_file.flush()
                return conf_file.name

        overridden_core = self.conf_base % conf_override
        self.conf_file_name = override_conf(conf_filepath, overridden_core)

        overridden_paste = ''
        if self.paste_conf_base:
            overridden_paste = self.paste_conf_base % conf_override
            override_conf(paste_conf_filepath, overridden_paste)

        overridden = ('==Core config==\n%s\n==Paste config==\n%s' %
                      (overridden_core, overridden_paste))

        return self.conf_file_name, overridden

    def start(self, expect_exit=True, expected_exitcode=0, **kwargs):
        """
        Starts the server.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """

        # Ensure the configuration file is written
        self.write_conf(**kwargs)

        elasticsearch_wrapper.ensure_elasticsearch()

        cmd = ("%(server_module)s --config-file %(conf_file_name)s"
               % {"server_module": self.server_module,
                  "conf_file_name": self.conf_file_name})
        cmd = "%s -m %s" % (sys.executable, cmd)
        # close the sock and release the unused port closer to start time
        if self.exec_env:
            exec_env = self.exec_env.copy()
        else:
            exec_env = {}
        pass_fds = set()
        if self.sock:
            if not self.fork_socket:
                self.sock.close()
                self.sock = None
            else:
                fd = os.dup(self.sock.fileno())
                exec_env[utils.SEARCHLIGHT_TEST_SOCKET_FD_STR] = str(fd)
                pass_fds.add(fd)
                self.sock.close()

        self.process_pid = test_utils.fork_exec(cmd,
                                                logfile=os.devnull,
                                                exec_env=exec_env,
                                                pass_fds=pass_fds)

        self.stop_kill = not expect_exit
        if self.pid_file:
            pf = open(self.pid_file, 'w')
            pf.write('%d\n' % self.process_pid)
            pf.close()
        if not expect_exit:
            rc = 0
            try:
                os.kill(self.process_pid, 0)
            except OSError:
                raise RuntimeError("The process did not start")
        else:
            rc = test_utils.wait_for_fork(
                self.process_pid,
                expected_exitcode=expected_exitcode)
        # avoid an FD leak
        if self.sock:
            os.close(fd)
            self.sock = None
        return (rc, '', '')

    def reload(self, expect_exit=True, expected_exitcode=0, **kwargs):
        """
        Start and stop the service to reload

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the servers.
        """
        self.stop()
        return self.start(expect_exit=expect_exit,
                          expected_exitcode=expected_exitcode, **kwargs)

    def stop(self):
        """
        Spin down the server.
        """
        if not self.process_pid:
            raise Exception('why is this being called? %s' % self.server_name)

        if self.stop_kill:
            os.kill(self.process_pid, signal.SIGTERM)
        rc = test_utils.wait_for_fork(self.process_pid, raise_error=False)
        return (rc, '', '')

    def dump_log(self, name):
        log = std_logging.getLogger(name)
        if not self.log_file or not os.path.exists(self.log_file):
            return
        fptr = open(self.log_file, 'r')
        for line in fptr:
            log.info(line.strip())


class SearchServer(Server):

    """
    Server object that starts/stops/manages the Search server.
    To be decided: where elasticsearch comes from.
    """

    def __init__(self, test_dir, port, policy_file, sock=None):
        super(SearchServer, self).__init__(test_dir, port, sock=sock)
        self.server_name = 'api'
        self.server_module = 'searchlight.cmd.%s' % self.server_name

        self.elasticsearch_port = elasticsearch_wrapper.elasticsearch_port
        self.pid_file = os.path.join(self.test_dir, "searchlight.pid")
        self.log_file = os.path.join(self.test_dir, "searchlight.log")
        self.api_version = 1
        self.policy_file = policy_file
        self.policy_default_rule = 'default'
        self.property_protection_rule_format = 'roles'

        self.service_policy_files = ''
        self.service_policy_path = ''

        self.conf_base = """[DEFAULT]
debug = %(debug)s
log_file = %(log_file)s
api_limit_max = 1000
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s

property_protection_file = %(property_protection_file)s
property_protection_rule_format = %(property_protection_rule_format)s

[paste_deploy]
flavor = %(deployment_flavor)s

[elasticsearch]
hosts = 127.0.0.1:%(elasticsearch_port)s

[service_policies]
service_policy_files = %(service_policy_files)s
service_policy_path = %(service_policy_path)s

[api]
# Hardcoding a single worker; the cleanup code can't deal with more
workers = 0
bind_host = 127.0.0.1
bind_port = %(bind_port)s

"""
        self.paste_conf_base = """[pipeline:searchlight]
pipeline = versionnegotiation unauthenticated-context rootapp

[pipeline:searchlight-keystone]
pipeline = versionnegotiation authtoken context rootapp

[pipeline:searchlight-trusted-auth]
pipeline = context rootapp

[composite:rootapp]
paste.composite_factory = searchlight.api:root_app_factory
/: apiversions
/v1: apiv1app

[app:apiversions]
paste.app_factory = searchlight.api.versions:create_resource

[app:apiv1app]
paste.app_factory = searchlight.api.v1.router:API.factory

[filter:versionnegotiation]
paste.filter_factory =
 searchlight.api.middleware.version_negotiation:VersionNegotiationFilter.factory

[filter:unauthenticated-context]
paste.filter_factory =
 searchlight.api.middleware.context:UnauthenticatedContextMiddleware.factory

[filter:authtoken]
paste.filter_factory = keystonemiddleware.auth_token:filter_factory
delay_auth_decision = true

[filter:context]
paste.filter_factory =
 searchlight.api.middleware.context:ContextMiddleware.factory
"""


class FunctionalTest(test_utils.BaseTestCase):

    """
    Base test class for any test that wants to test the actual
    servers and clients and not just the stubbed out interfaces
    """

    inited = False
    disabled = False
    launched_servers = []

    @test_utils.depends_on_exe("elasticsearch")
    @test_utils.skip_if_disabled
    def setUp(self):
        super(FunctionalTest, self).setUp()
        self.test_dir = self.useFixture(fixtures.TempDir()).path

        self.api_protocol = 'http'
        self.api_port, search_sock = test_utils.get_unused_port_and_socket()

        self.tracecmd = tracecmd_osmap.get(platform.system())

        self.conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(self.conf_dir)
        self.copy_data_file('policy.json', self.conf_dir)
        self.copy_data_file('property-protections.conf', self.conf_dir)
        self.copy_data_file('property-protections-policies.conf',
                            self.conf_dir)
        self.property_file_roles = os.path.join(self.conf_dir,
                                                'property-protections.conf')
        property_policies = 'property-protections-policies.conf'
        self.property_file_policies = os.path.join(self.conf_dir,
                                                   property_policies)
        self.policy_file = os.path.join(self.conf_dir, 'policy.json')

        self.api_server = SearchServer(self.test_dir,
                                       self.api_port,
                                       self.policy_file,
                                       sock=search_sock)
        self._additional_server_config()

        self.pid_files = [self.api_server.pid_file]
        self.files_to_destroy = []
        self.launched_servers = []

        self.elastic_connection = elasticsearch.Elasticsearch(
            "http://localhost:%s" % self.api_server.elasticsearch_port)

        self.api_server.deployment_flavor = "trusted-auth"
        # Use the role-based policy file all over; we need it for the property
        # protection tests
        self.api_server.property_protection_file = self.property_file_roles

        self.base_url = "http://127.0.0.1:%d/v1" % self.api_port
        self.start_with_retry(self.api_server,
                              "api_port",
                              max_retries=3,
                              **self.__dict__.copy())
        self.addCleanup(self.cleanup)

        self.initialized_plugins = {}
        self.configurePlugins()

    def _additional_server_config(self):
        """Any additional configuration for the API server. This is run prior
        to writing the server config file and starting the server.
        """
        pass

    def configurePlugins(self, include_plugins=None, exclude_plugins=()):
        """Specify 'exclude_plugins' or 'include_plugins' as a list of
        tuples.
        """
        plugin_classes = {
            'glance': {'images': 'ImageIndex', 'metadefs': 'MetadefIndex'},
            'nova': {'servers': 'ServerIndex',
                     'hypervisors': 'HypervisorIndex',
                     'flavors': 'FlavorIndex',
                     'servergroups': 'ServerGroupIndex'},
            'cinder': {'volumes': 'VolumeIndex', 'snapshots': 'SnapshotIndex'},
            'neutron': {'networks': 'NetworkIndex', 'ports': 'PortIndex',
                        'subnets': 'SubnetIndex', 'routers': 'RouterIndex',
                        'floatingips': 'FloatingIPIndex',
                        'security_groups': 'SecurityGroupIndex'},
            'swift': {'accounts': 'AccountIndex',
                      'containers': 'ContainerIndex',
                      'objects': 'ObjectIndex'},
            'designate': {'zones': 'ZoneIndex',
                          'recordsets': 'RecordSetIndex'}
        }

        plugins = include_plugins or (
            ('glance', 'images'), ('glance', 'metadefs'),
            ('nova', 'servers'), ('nova', 'hypervisors'),
            ('nova', 'flavors'), ('nova', 'servergroups'),
            ('cinder', 'volumes'), ('cinder', 'snapshots'),
            ('neutron', 'networks'), ('neutron', 'ports'),
            ('neutron', 'subnets'), ('neutron', 'routers'),
            ('neutron', 'floatingips'), ('neutron', 'security_groups'),
            ('cinder', 'volumes'), ('cinder', 'snapshots'),
            ('swift', 'accounts'), ('swift', 'containers'),
            ('swift', 'objects'),
            ('designate', 'zones'), ('designate', 'recordsets')
        )
        plugins = filter(lambda plugin: plugin not in exclude_plugins, plugins)

        # Make sure the plugins instantiated in this process use the same
        # connection as the ones in the API process they'll work with
        es_conn_patcher = mock.patch('searchlight.elasticsearch.get_api',
                                     return_value=self.elastic_connection)
        es_conn_patcher.start()
        self.addCleanup(es_conn_patcher.stop)

        index_name = es_utils.create_new_index('searchlight')

        for service, plugin_type in plugins:
            plugin_mod_name = ("searchlight.elasticsearch.plugins.%s.%s"
                               % (service, plugin_type))
            plugin_cls_name = plugin_classes[service][plugin_type]

            plugin_mod = importlib.import_module(plugin_mod_name)
            plugin_cls = getattr(plugin_mod, plugin_cls_name)

            # This'll call our dummy init (above)
            plugin_instance = plugin_cls()

            self.initialized_plugins[plugin_instance.document_type] = \
                plugin_instance

        # Reproduce the logic from searchlight.common.utils to set up
        # parent/child relationships; the stevedore structure is different
        for instance in self.initialized_plugins.values():
            parent_plugin_name = instance.parent_plugin_type()
            if parent_plugin_name:
                parent_plugin = self.initialized_plugins[parent_plugin_name]
                instance.register_parent(parent_plugin)

        # Reproduce the logic from cmd.manage to prepare the index.
        for instance in self.initialized_plugins.values():
            instance.prepare_index(index_name=index_name)

        # Create the aliases
        es_utils.setup_alias(index_name, 'searchlight-search',
                             'searchlight-listener')

    def tearDown(self):
        super(FunctionalTest, self).tearDown()

        self.api_server.dump_log('api_server')

    def _index(self, plugin, docs, refresh_index=True):
        """Index data exactly as the plugin would under searchlight-manage.
        docs must be an iterable of whatever the plugin's 'get_objects' call
        would return.
        """
        with mock.patch.object(plugin, 'get_objects', return_value=docs):
            with mock.patch.object(plugin, 'child_plugins', return_value=[]):
                if hasattr(plugin, 'get_rbac_objects'):
                    rbac_mock = mock.patch.object(plugin, 'get_rbac_objects',
                                                  return_value={})
                    rbac_mock.start()
                plugin.index_initial_data()

        if refresh_index:
            # Force elasticsearch to update its search index
            self._flush_elasticsearch(plugin.alias_name_listener)

    def _flush_elasticsearch(self, index_name=None):
        self.elastic_connection.indices.flush(index_name)

    def _headers(self, tenant_id, custom_headers={}):
        base_headers = {
            "X-Identity-Status": "Confirmed",
            "X-Auth-Token": "932c5c84-02ac-4fe5-a9ba-620af0e2bb96",
            "X-User-Id": "f9a41d13-0c13-47e9-bee2-ce4e8bfe958e",
            "X-Tenant-Id": tenant_id,
            "X-Roles": "member",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        base_headers.update(custom_headers)
        return base_headers

    def _request(self, method, uri, tenant, body=None,
                 role="member", decode_json=True, extra_headers={}):
        custom_headers = {
            "X-Tenant-Id": tenant,
            "X-Roles": role,
        }
        custom_headers.update(extra_headers)
        headers = self._headers(tenant, custom_headers)
        if not tenant:
            del headers['X-Tenant-Id']
        kwargs = {
            "headers": headers
        }
        if body:
            kwargs["data"] = jsonutils.dumps(body)

        response = requests.request(
            method,
            self.base_url + uri,
            **kwargs
        )
        content = response.content
        if decode_json:
            content = response.json()
        return response, content

    def _search_request(self, body, tenant, role="member", decode_json=True,
                        is_admin_project=None):
        """Conduct a search against all elasticsearch indices unless specified
        in `body`. Returns the response and json-decoded content.
        """
        extra_headers = {}
        if is_admin_project is not None:
            extra_headers['X-Is-Admin-Project'] = str(is_admin_project)

        return self._request("POST", "/search", tenant, body,
                             role, decode_json, extra_headers)

    def _facet_request(self, tenant, doc_type=None, role="member",
                       decode_json=True, include_fields=None,
                       exclude_options=None):
        url = "/search/facets"
        params = {}
        if doc_type:
            params['type'] = doc_type
        if include_fields is not None:
            params['include_fields'] = "true" if include_fields else "false"
        if exclude_options is not None:
            params['exclude_options'] = "true" if exclude_options else "false"
        url += '?' + urllib.parse.urlencode(params)
        return self._request("GET", url, tenant, role=role,
                             decode_json=decode_json)

    def _plugin_list_request(self, tenant, role="member"):
        url = "/search/plugins"
        return self._request("GET", url, tenant, role=role)

    def _get_hit_source(self, es_response):
        """Parse the _source from the elasticsearch hits"""
        if isinstance(es_response, str):
            es_response = jsonutils.loads(es_response)
        return [h["_source"] for h in es_response["hits"]["hits"]]

    def _get_all_elasticsearch_docs(self, indices=[]):
        """Query ES and return all documents. The caller can specify a list
           of indices to query. If the list is empty, we will query all
            indices.
        """
        index = ','.join(indices)
        es_url = "http://localhost:%s/%s/_search" % (
            self.api_server.elasticsearch_port, index)
        response = requests.get(es_url)
        self.assertEqual(200, response.status_code)
        return response.json()

    def _get_elasticsearch_doc(self, index_name, doc_type, doc_id):
        es_url = "http://localhost:%s/%s/%s/%s" % (
            self.api_server.elasticsearch_port, index_name, doc_type, doc_id)

        response = requests.get(es_url)
        return response.json()

    def _delete_elasticsearch_doc(self, index_name, doc_type, doc_id):
        es_url = "http://localhost:%s/%s/%s/%s" % (
            self.api_server.elasticsearch_port, index_name, doc_type, doc_id)

        response = requests.delete(es_url)
        return response.json()

    def _get_elasticsearch_aliases(self, indices):
        """Return all aliases associated with a specified index(es). The
           caller can specify a list of indices. If the list is empty, we
           will query all indices.
        """
        index = ','.join(indices)
        es_url = "http://localhost:%s/%s/_aliases" % (
            self.api_server.elasticsearch_port, index)
        response = requests.get(es_url)
        return response.json()

    def _load_fixture_data(self, name):
        base_dir = "searchlight/tests/functional/data"
        # binary mode is needed due to bug/1515231
        with open(os.path.join(base_dir, name), 'r+b') as f:
            return jsonutils.load(f)

    def set_policy_rules(self, rules):
        fap = open(self.policy_file, 'w')
        fap.write(jsonutils.dumps(rules))
        fap.close()

    def cleanup(self):
        """
        Makes sure anything we created or started up in the
        tests are destroyed or spun down
        """

        # NOTE(jbresnah) call stop on each of the servers instead of
        # checking the pid file.  stop() will wait until the child
        # server is dead.  This eliminates the possibility of a race
        # between a child process listening on a port actually dying
        # and a new process being started
        servers = [self.api_server]
        for s in servers:
            try:
                s.stop()
            except Exception:
                pass

        for f in self.files_to_destroy:
            if os.path.exists(f):
                os.unlink(f)

        for plugin_instance in self.initialized_plugins.values():
            self.elastic_connection.indices.delete(
                index=plugin_instance.alias_name_search,
                ignore=404)
            self.elastic_connection.indices.delete(
                index=plugin_instance.alias_name_listener,
                ignore=404)

    def start_server(self,
                     server,
                     expect_launch,
                     expect_exit=True,
                     expected_exitcode=0,
                     **kwargs):
        """
        Starts a server on an unused port.

        Any kwargs passed to this method will override the configuration
        value in the conf file used in starting the server.

        :param server: the server to launch
        :param expect_launch: true iff the server is expected to
                              successfully start
        :param expect_exit: true iff the launched process is expected
                            to exit in a timely fashion
        :param expected_exitcode: expected exitcode from the launcher
        """
        self.cleanup()

        # Start up the requested server
        exitcode, out, err = server.start(expect_exit=expect_exit,
                                          expected_exitcode=expected_exitcode,
                                          **kwargs)
        if expect_exit:
            self.assertEqual(expected_exitcode, exitcode,
                             "Failed to spin up the requested server. "
                             "Got: %s" % err)

        self.launched_servers.append(server)

        launch_msg = self.wait_for_servers([server], expect_launch)
        self.assertIsNone(launch_msg, launch_msg)

    def start_with_retry(self, server, port_name, max_retries,
                         expect_launch=True,
                         **kwargs):
        """
        Starts a server, with retries if the server launches but
        fails to start listening on the expected port.

        :param server: the server to launch
        :param port_name: the name of the port attribute
        :param max_retries: the maximum number of attempts
        :param expect_launch: true iff the server is expected to
                              successfully start
        :param expect_exit: true iff the launched process is expected
                            to exit in a timely fashion
        """
        launch_msg = None
        for i in range(max_retries):
            exitcode, out, err = server.start(expect_exit=not expect_launch,
                                              **kwargs)
            name = server.server_name
            self.assertEqual(0, exitcode,
                             "Failed to spin up the %s server. "
                             "Got: %s" % (name, err))
            launch_msg = self.wait_for_servers([server], expect_launch)
            if launch_msg:
                server.stop()
                server.bind_port = get_unused_port()
                setattr(self, port_name, server.bind_port)
            else:
                self.launched_servers.append(server)
                break
        self.assertIsNone(launch_msg, launch_msg)

    def ping_server(self, port):
        """
        Simple ping on the port. If responsive, return True, else
        return False.

        :note We use raw sockets, not ping here, since ping uses ICMP and
        has no concept of ports...
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except socket.error:
            return False

    def wait_for_servers(self, servers, expect_launch=True, timeout=10):
        """
        Tight loop, waiting for the given server port(s) to be available.
        Returns when all are pingable. There is a timeout on waiting
        for the servers to come up.

        :param servers: Searchlight server ports to ping
        :param expect_launch: Optional, true iff the server(s) are
                              expected to successfully start
        :param timeout: Optional, defaults to 10 seconds
        :return: None if launch expectation is met, otherwise an
                 assertion message
        """
        now = datetime.datetime.now()
        timeout_time = now + datetime.timedelta(seconds=timeout)
        replied = []
        while (timeout_time > now):
            pinged = 0
            for server in servers:
                if self.ping_server(server.bind_port):
                    pinged += 1
                    if server not in replied:
                        replied.append(server)
            if pinged == len(servers):
                msg = 'Unexpected server launch status'
                return None if expect_launch else msg
            now = datetime.datetime.now()
            time.sleep(0.05)

        failed = list(set(servers) - set(replied))
        msg = 'Unexpected server launch status for: '
        for f in failed:
            msg += ('%s, ' % f.server_name)
            if os.path.exists(f.pid_file):
                pid = f.process_pid
                trace = f.pid_file.replace('.pid', '.trace')
                if self.tracecmd:
                    cmd = '%s -p %d -o %s' % (self.tracecmd, pid, trace)
                    execute(cmd, raise_error=False, expect_exit=False)
                    time.sleep(0.5)
                    if os.path.exists(trace):
                        msg += ('\n%s:\n%s\n' % (self.tracecmd,
                                                 open(trace).read()))

        self.add_log_details(failed)

        return msg if expect_launch else None

    def stop_server(self, server, name):
        """
        Called to stop a single server in a normal fashion using the
        searchlight-control stop method to gracefully shut the server down.

        :param server: the server to stop
        """
        # Spin down the requested server
        server.stop()

    def stop_servers(self):
        """
        Called to stop the started servers in a normal fashion. Note
        that cleanup() will stop the servers using a fairly draconian
        method of sending a SIGTERM signal to the servers. Here, we use
        the searchlight-control stop method to gracefully shut the server down.
        This method also asserts that the shutdown was clean, and so it
        is meant to be called during a normal test case sequence.
        """

        # Spin down the API server
        self.stop_server(self.api_server, 'API server')

    def copy_data_file(self, file_name, dst_dir):
        src_file_name = os.path.join('searchlight/tests/etc', file_name)
        shutil.copy(src_file_name, dst_dir)
        dst_file_name = os.path.join(dst_dir, file_name)
        return dst_file_name

    def add_log_details(self, servers=None):
        logs = [s.log_file for s in (servers or self.launched_servers)]
        for log in logs:
            if os.path.exists(log):
                testtools.content.attach_file(self, log)


class ElasticsearchWrapper(object):
    """Helper to make sure elasticsearch is running. Tests should clear up
    after themselves because they'll be using a shared instance to avoid
    a ~5 second startup time
    """
    def __init__(self):
        self.elasticsearch_pid = None
        self._elasticsearch_port = None

    @property
    def elasticsearch_port(self):
        if self._elasticsearch_port is None:
            self._elasticsearch_port = get_unused_port()
        return self._elasticsearch_port

    def ensure_elasticsearch(self):
        """Start elasticsearch if it's not already running"""
        if self.elasticsearch_pid:
            # Use the existing instance
            return

        # Create a random directory and get or assign a port
        elasticsearch_root_dir = tempfile.mkdtemp(prefix='elastic')
        es_options = {
            'node.local': 'true',
            'index.number_of_shards': 1,
            'index.number_of_replicas': 0,
            'network.host': '127.0.0.1',
            'http.port': self.elasticsearch_port,
            'discovery.zen.ping.multicast.enabled': 'false',
            'path.data': elasticsearch_root_dir,
            'path.conf': elasticsearch_root_dir,
            'path.logs': elasticsearch_root_dir,
            'action.auto_create_index': 'false',
            'script.engine.groovy.inline.update': 'on'
        }
        # Set JVM options
        exec_env = {
            'ES_HEAP_SIZE': '64m'
        }
        cmd = 'elasticsearch '
        cmd += ' '.join('--%s=%s' % kv for kv in es_options.items())
        # Fork and retain the PID
        self.elasticsearch_pid = test_utils.fork_exec(cmd,
                                                      logfile=os.devnull,
                                                      exec_env=exec_env)

        # Register a shutdown function
        def _stop_elasticsearch():
            if not self.elasticsearch_pid:
                raise Exception('why is this being called? elasticsearch')
            os.kill(self.elasticsearch_pid, signal.SIGTERM)
            rc = test_utils.wait_for_fork(self.elasticsearch_pid,
                                          raise_error=False)
            self.elasticsearch_pid = None
            # Delete the temporary directory
            shutil.rmtree(elasticsearch_root_dir)
            return (rc, '', '')

        atexit.register(_stop_elasticsearch)

        # Wait for elasticsearch to spin up; it takes a while to initialize
        es_url = 'http://localhost:%s' % self.elasticsearch_port
        time.sleep(10)
        for _ in range(10):
            try:
                response = requests.get(es_url)
                if response.status_code == 200:
                    break
            except requests.exceptions.RequestException as e:
                LOG.debug("ES startup: Request Exception occured: %s" % e)
            time.sleep(10)
        else:
            raise Exception("Elasticsearch failed to start")


elasticsearch_wrapper = ElasticsearchWrapper()
