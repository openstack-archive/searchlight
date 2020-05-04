#!/usr/bin/env python

# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
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

from urllib import parse as urlparse

import os
from oslo_config import cfg
import oslo_messaging
from oslo_serialization import jsonutils
import sys
import time

topic = 'notifications'
password = os.environ.get('RABBIT_PASSWORD', os.environ.get('OS_PASSWORD'))
host = urlparse.urlparse(os.environ.get('OS_AUTH_URL')).hostname
username = os.environ.get('RABBIT_USER', 'stackrabbit')


class EP(object):
    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        all_locals = locals()
        all_locals.pop('self')
        print(jsonutils.dumps(all_locals))

    def error(self, ctxt, publisher_id, event_type, payload, metadata):
        all_locals = locals()
        all_locals.pop('self')
        print(jsonutils.dumps(all_locals))


def main():
    if len(sys.argv) < 2:
        print("Supply an exchange")
        sys.exit(0)

    exchange = sys.argv[1]
    pool = sys.argv[2] if len(sys.argv) > 2 else None

    transport = oslo_messaging.get_notification_transport(
        cfg.CONF,
        url='rabbit://%s:%s@%s' % (username, password, host))
    targets = [oslo_messaging.Target(topic=topic, exchange=exchange)]
    endpoints = [EP()]
    oslo_listener = oslo_messaging.get_notification_listener(
        transport, targets, endpoints, pool=pool, executor='threading')
    try:
        print("Started")
        oslo_listener.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping")
        oslo_listener.stop()
        oslo_listener.wait()


if __name__ == '__main__':
    main()
