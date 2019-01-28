# Copyright 2014 Red Hat, Inc.
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

from oslo_i18n import get_available_languages  # noqa
from oslo_i18n import translate  # noqa
from oslo_i18n import TranslatorFactory  # noqa

_translators = TranslatorFactory(domain='searchlight')

# The primary translation function using the well-known name "_"
_ = _translators.primary
