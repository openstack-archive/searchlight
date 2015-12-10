# Copyright 2016 Hewlett-Packard Corporation
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

import copy
import mock

from searchlight.elasticsearch.plugins import base

ROLE_SEPARATED_DATA = [
    {
        "id": "role-fake1",
        "public_field": "this is public",
        "admin_wildcard_this": "this is admin only",
        "admin_wildcard_that": "this is admin too",
        "admin_specific": "specific admin field",
        "tenant_id": "tenant1",
        "updated_at": "2015-08-06T12:48:14.000000"
    },
    {
        "id": "role-fake2",
        "public_field": "still public",
        "admin_wildcard_this": "still admin",
        "admin_wildcard_that": "still admin too",
        "admin_specific": "specific admin field",
        "tenant_id": "tenant1",
        "updated_at": "2015-08-06T12:48:14.000000"
    }
]


NON_ROLE_SEPARATED_DATA = [
    {
        "id": "non-role-fake1",
        "public_field": "this is public",
        "tenant_id": "tenant1",
        "updated_at": "2015-08-06T12:48:14.000000"
    },
    {
        "id": "non-role-fake2",
        "public_field": "still public",
        "tenant_id": "tenant1",
        "updated_at": "2015-08-06T12:48:14.000000"
    }
]


SIMPLE_DATA = [
    {
        "id": "simple1"
    }
]


CHILD_DATA = [
    {
        "id": "child1",
        "parent_id": "simple1"
    }
]


class FakePluginBase(base.IndexBase):
    NotificationHandlerCls = base.NotificationBase

    def __init__(self, es_engine):
        self.options = mock.Mock()
        self.options.admin_only_fields = None
        self.options.index_name = 'fake'
        self.options.enabled = True

        self.engine = es_engine
        self.index_name = 'fake'
        self.document_type = self.get_document_type()

        self.parent_plugin = None
        self.child_plugins = []

    def serialize(self, doc):
        return doc

    def _get_rbac_field_filters(self, request_context):
        return []


class RoleSeparatedPlugin(FakePluginBase):
    def __init__(self, es_engine):
        super(RoleSeparatedPlugin, self).__init__(es_engine)
        self.options.admin_only_fields = 'admin_wildcard_*,admin_specific'

    @classmethod
    def get_document_type(cls):
        return 'role-separated'

    def get_mapping(self):
        return {
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'public_field': {'type': 'string'},
                'admin_wildcard_this': {'type': 'string'},
                'admin_wildcard_that': {'type': 'string'},
                'admin_specific': {'type': 'string'},
                'tenant_id': {'type': 'string'}
            }
        }

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

    def get_objects(self):
        self.number_documents = len(ROLE_SEPARATED_DATA)
        return copy.deepcopy(ROLE_SEPARATED_DATA)

    def serialize(self, doc):
        return doc


class NonRoleSeparatedPlugin(FakePluginBase):
    def __init__(self, es_engine):
        super(NonRoleSeparatedPlugin, self).__init__(es_engine)

    @classmethod
    def get_document_type(cls):
        return 'not-role-separated'

    def get_mapping(self):
        return {
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'public_field': {'type': 'string'},
                'tenant_id': {'type': 'string'}
            }
        }

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

    def get_objects(self):
        self.number_documents = len(NON_ROLE_SEPARATED_DATA)
        return copy.deepcopy(NON_ROLE_SEPARATED_DATA)

    def serialize(self, doc):
        return doc


class FakeSimplePlugin(FakePluginBase):
    def __init__(self, es_engine):
        super(FakeSimplePlugin, self).__init__(es_engine)

    @classmethod
    def get_document_type(cls):
        return 'fake-simple'

    def get_mapping(self):
        return {
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'}
            }
        }

    def get_objects(self):
        self.number_documents = len(SIMPLE_DATA)
        return copy.deepcopy(SIMPLE_DATA)


class FakeChildPlugin(FakePluginBase):
    def __init__(self, es_engine):
        super(FakeChildPlugin, self).__init__(es_engine)

    @classmethod
    def get_document_type(cls):
        return 'fake-child'

    def get_mapping(self):
        # Explicit parent is not necessary; it'll get added
        return {
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'parent_id': {'type': 'string', 'index': 'not_analyzed'}
            }
        }

    @classmethod
    def parent_plugin_type(cls):
        return "fake-simple"

    @property
    def parent_id_field(self):
        return 'parent_id'

    def get_objects(self):
        self.number_documents = len(CHILD_DATA)
        return copy.deepcopy(CHILD_DATA)
