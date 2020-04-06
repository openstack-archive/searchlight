# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
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
from unittest import mock

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

ROUTING_DATA = [
    {
        "id": "id_for_routing_plugin-fake1",
        "tenant_id": "tenant1",
    }
]

SIMPLE_DATA = [
    {
        "id": "simple1",
        "updated_at": "2015-08-06T12:48:14.000000"
    }
]


CHILD_DATA = [
    {
        "id": "child1",
        "parent_id": "simple1",
        "updated_at": "2015-08-06T12:48:14.000000"
    }
]


class FakePluginBase(base.IndexBase):
    NotificationHandlerCls = base.NotificationBase

    def __init__(self, es_engine):
        self.options = mock.Mock()
        self.options.admin_only_fields = None
        self.options.resource_group_name = 'searchlight'
        self.options.enabled = True
        self.options.mapping_use_doc_values = True
        self.options.override_region_name = None

        self.engine = es_engine
        self.document_type = self.get_document_type()
        self.parent_plugin = None
        self.child_plugins = []

    def serialize(self, doc):
        return doc

    def _get_rbac_field_filters(self, request_context):
        return []

    @property
    def resource_allowed_policy_target(self):
        return None

    @property
    def service_type(self):
        return None


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
                'tenant_id': {'type': 'string'},
                'faceted': {'type': 'short'}
            }
        }

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

    @property
    def facets_with_options(self):
        return ('faceted',)

    def get_objects(self):
        self.number_documents = len(NON_ROLE_SEPARATED_DATA)
        return copy.deepcopy(NON_ROLE_SEPARATED_DATA)

    def serialize(self, doc):
        return doc


class FakeSimpleRoutingPlugin(FakePluginBase):
    def __init__(self, es_engine):
        super(FakeSimpleRoutingPlugin, self).__init__(es_engine)

    @classmethod
    def get_document_type(cls):
        return 'Fake-RoutingPlugin'

    def get_mapping(self):
        return {
            'properties': {
                'id': {'type': 'string', 'index': 'not_analyzed'},
                'tenant_id': {'type': 'string'}
            }
        }

    def _get_rbac_field_filters(self, request_context):
        return [
            {'term': {'tenant_id': request_context.owner}}
        ]

    @property
    def routing_field(self):
        return "tenant_id"

    def get_objects(self):
        self.number_documents = len(ROUTING_DATA)
        return copy.deepcopy(ROUTING_DATA)

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

    def get_parent_id_field(self):
        return 'parent_id'

    def get_objects(self):
        self.number_documents = len(CHILD_DATA)
        return copy.deepcopy(CHILD_DATA)


class FakeWrongGroupChildPlugin(FakeChildPlugin):
    def __init__(self, es_engine):
        super(FakeWrongGroupChildPlugin, self).__init__(es_engine)
        self.options.resource_group_name = 'wrong-group-name'

    @classmethod
    def get_document_type(cls):
        return 'fake-wrong-index-child'


class FakeWrongGroupGrandchildPlugin(FakeChildPlugin):
    def __init__(self, es_engine):
        super(FakeWrongGroupGrandchildPlugin, self).__init__(es_engine)
        self.options.resource_group_name = 'wrong-group-name'

    @classmethod
    def get_document_type(cls):
        return 'fake-wrong-index-grand-child'

    @classmethod
    def parent_plugin_type(cls):
        return "fake-wrong-index-child"


class FakeSeparatedChildPlugin(FakePluginBase):
    def __init__(self, es_engine):
        super(FakeSeparatedChildPlugin, self).__init__(es_engine)

    @classmethod
    def get_document_type(cls):
        return 'fake-role-separated-child'

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
        return "role-separated"

    def get_parent_id_field(self):
        return 'parent_id'

    @property
    def requires_role_separation(self):
        return True

    def get_objects(self):
        self.number_documents = len(CHILD_DATA)
        return copy.deepcopy(CHILD_DATA)
