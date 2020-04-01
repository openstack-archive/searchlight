# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

from oslo_config import cfg
from oslo_service import service as os_service

from searchlight import listener
from searchlight import service


CONF = cfg.CONF
CONF.import_group("listener", "searchlight.listener")


def main():
    service.prepare_service()
    launcher = os_service.ProcessLauncher(CONF, restart_method='mutate')
    launcher.launch_service(
        listener.ListenerService(),
        workers=CONF.listener.workers)
    launcher.wait()


if __name__ == "__main__":
    main()
