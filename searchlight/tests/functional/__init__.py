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
import httplib2
import logging
import os
import platform
import shutil
import signal
import six
import socket
import sys
import tempfile
import time

import fixtures
from oslo_serialization import jsonutils
# NOTE(jokke): simplified transition to py3, behaves like py2 xrange
from six.moves import range
import testtools

from searchlight.common import utils
from searchlight.tests import utils as test_utils

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
        self.verbose = True
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
                exec_env[utils.GLANCE_TEST_SOCKET_FD_STR] = str(fd)
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
        log = logging.getLogger(name)
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
        self.workers = 0
        self.api_version = 1
        self.policy_file = policy_file
        self.policy_default_rule = 'default'
        self.property_protection_rule_format = 'roles'

        self.conf_base = """[DEFAULT]
verbose = %(verbose)s
debug = %(debug)s
bind_host = 127.0.0.1
bind_port = %(bind_port)s
log_file = %(log_file)s
api_limit_max = 1000
workers = %(workers)s
policy_file = %(policy_file)s
policy_default_rule = %(policy_default_rule)s

property_protection_file = %(property_protection_file)s
property_protection_rule_format = %(property_protection_rule_format)s

[paste_deploy]
flavor = %(deployment_flavor)s

[elasticsearch]
hosts = 127.0.0.1:%(elasticsearch_port)s
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

    def setUp(self):
        super(FunctionalTest, self).setUp()
        self.test_dir = self.useFixture(fixtures.TempDir()).path

        self.api_protocol = 'http'
        self.api_port, search_sock = test_utils.get_unused_port_and_socket()

        self.tracecmd = tracecmd_osmap.get(platform.system())

        conf_dir = os.path.join(self.test_dir, 'etc')
        utils.safe_mkdirs(conf_dir)
        self.copy_data_file('policy.json', conf_dir)
        self.copy_data_file('property-protections.conf', conf_dir)
        self.copy_data_file('property-protections-policies.conf', conf_dir)
        self.property_file_roles = os.path.join(conf_dir,
                                                'property-protections.conf')
        property_policies = 'property-protections-policies.conf'
        self.property_file_policies = os.path.join(conf_dir,
                                                   property_policies)
        self.policy_file = os.path.join(conf_dir, 'policy.json')

        self.api_server = SearchServer(self.test_dir,
                                       self.api_port,
                                       self.policy_file,
                                       sock=search_sock)

        self.pid_files = [self.api_server.pid_file]
        self.files_to_destroy = []
        self.launched_servers = []

    def tearDown(self):
        if not self.disabled:
            self.cleanup()

        super(FunctionalTest, self).tearDown()

        self.api_server.dump_log('api_server')

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
        self.assertTrue(launch_msg is None, launch_msg)

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
        self.assertTrue(launch_msg is None, launch_msg)

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
        :param timeout: Optional, defaults to 3 seconds
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
            'discovery.zen.ping.multicast.disabled': 'false',
            'path.data': elasticsearch_root_dir,
            'action.auto_create_index': False,
            'script.engine.groovy.inline.update': 'on'
        }
        # Set JVM options
        exec_env = {
            'ES_HEAP_SIZE': '20m'
        }
        cmd = 'elasticsearch '
        cmd += ' '.join('--%s=%s' % kv for kv in six.iteritems(es_options))

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
        http = httplib2.Http()
        es_url = 'http://localhost:%s' % self.elasticsearch_port
        for _ in range(6):
            try:
                response, content = http.request(es_url)
                if response.status == 200:
                    break
            except socket.error:
                # Expect 'connection refused' a couple of times
                pass
            time.sleep(5)
        else:
            raise Exception("Elasticsearch failed to start ")


elasticsearch_wrapper = ElasticsearchWrapper()
