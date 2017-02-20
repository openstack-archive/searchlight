# Copyright 2012 OpenStack Foundation.
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

from oslo_concurrency import lockutils
from oslo_config import cfg

from searchlight.common import wsgi

CONF = cfg.CONF

_CACHED_THREAD_POOL = {}


def memoize(lock_name):
    def memoizer_wrapper(func):
        @lockutils.synchronized(lock_name)
        def memoizer(lock_name):
            if lock_name not in _CACHED_THREAD_POOL:
                _CACHED_THREAD_POOL[lock_name] = func()

            return _CACHED_THREAD_POOL[lock_name]

        return memoizer(lock_name)

    return memoizer_wrapper


def get_thread_pool(lock_name, size=1024):
    """Initializes eventlet thread pool.

    If thread pool is present in cache, then returns it from cache
    else create new pool, stores it in cache and return newly created
    pool.

    @param lock_name:  Name of the lock.
    @param size: Size of eventlet pool.

    @return: eventlet pool
    """
    @memoize(lock_name)
    def _get_thread_pool():
        return wsgi.get_asynchronous_eventlet_pool(size=size)

    return _get_thread_pool
