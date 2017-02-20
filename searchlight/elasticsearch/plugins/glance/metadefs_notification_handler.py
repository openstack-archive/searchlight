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

from searchlight.elasticsearch.plugins import base
from searchlight import pipeline


class MetadefHandler(base.NotificationBase):

    def __init__(self, *args, **kwargs):
        super(MetadefHandler, self).__init__(*args, **kwargs)
        self.namespace_delete_keys = ['deleted_at', 'deleted',
                                      'namespace_old']
        self.property_delete_keys = ['deleted', 'deleted_at',
                                     'name_old', 'namespace']

    @classmethod
    def _get_notification_exchanges(cls):
        return ['glance']

    def get_event_handlers(self):
        return {
            "metadef_namespace.create": self.create_ns,
            "metadef_namespace.update": self.update_ns,
            "metadef_namespace.delete": self.delete_ns,
            "metadef_object.create": self.create_obj,
            "metadef_object.update": self.update_obj,
            "metadef_object.delete": self.delete_obj,
            "metadef_property.create": self.create_prop,
            "metadef_property.update": self.update_prop,
            "metadef_property.delete": self.delete_prop,
            "metadef_resource_type.create": self.create_rs,
            "metadef_resource_type.delete": self.delete_rs,
            "metadef_tag.create": self.create_tag,
            "metadef_tag.update": self.update_tag,
            "metadef_tag.delete": self.delete_tag,
            "metadef_namespace.delete_properties": self.delete_props,
            "metadef_namespace.delete_objects": self.delete_objects,
            "metadef_namespace.delete_tags": self.delete_tags
        }

    def get_log_fields(self, event_type, payload):
        return ('namespace', payload.get('namespace')),

    def create_ns(self, event_type, payload, timestamp):
        namespace = self.format_namespace(payload)
        self.index_helper.save_document(
            namespace,
            version=self.get_version(namespace, timestamp))
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  namespace
                                  )

    def update_ns(self, event_type, payload, timestamp):
        # Update operation in es doesn't support external version,
        # so we have to manually update the doc and reindex it.
        namespace_es = self.index_helper.get_document(
            payload['namespace_old'], for_admin=True)
        namespace = self.format_namespace(payload)
        namespace_es['_source'].update(namespace)
        self.index_helper.save_document(
            namespace_es['_source'],
            version=self.get_version(namespace, timestamp))
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  namespace_es['_source'])

    def delete_ns(self, event_type, payload, timestamp):
        id = payload['namespace']
        self.index_helper.delete_document({'_id': id})
        return pipeline.DeleteItem(self.index_helper.plugin,
                                   event_type,
                                   payload,
                                   id
                                   )

    def create_obj(self, event_type, payload, timestamp):
        id = payload['namespace']
        object = self.format_object(payload)
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.create_entity(preexisting['_source'], 'objects', object)
        self.index_helper.save_document(
            preexisting['_source'], preexisting['_version'] + 1
        )
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def update_obj(self, event_type, payload, timestamp):
        id = payload['namespace']
        object = self.format_object(payload)
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.update_entity(
            preexisting['_source'], "objects",
            payload['name_old'],
            object,
            "name")
        self.index_helper.save_document(
            preexisting['_source'], preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def delete_obj(self, event_type, payload, timestamp):
        id = payload['namespace']
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.delete_entity(
            preexisting['_source'], "objects", payload['name'], "name")
        self.index_helper.save_document(
            preexisting['_source'], preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def create_prop(self, event_type, payload, timestamp):
        id = payload['namespace']
        property = self.format_property(payload)
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.create_entity(preexisting['_source'], 'properties', property)
        self.index_helper.save_document(
            preexisting['_source'], preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def update_prop(self, event_type, payload, timestamp):
        id = payload['namespace']
        property = self.format_property(payload)
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.update_entity(
            preexisting['_source'],
            "properties",
            payload['name_old'],
            property,
            "name")
        self.index_helper.save_document(
            preexisting['_source'], preexisting['_version'] + 1
        )
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def delete_prop(self, event_type, payload, timestamp):
        id = payload['namespace']
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.delete_entity(
            preexisting['_source'], "properties", payload['name'], "name")
        self.index_helper.save_document(preexisting['_source'],
                                        preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def create_rs(self, event_type, payload, timestamp):
        id = payload['namespace']
        resource_type = {}
        resource_type['name'] = payload['name']
        if payload['prefix']:
            resource_type['prefix'] = payload['prefix']
        if payload['properties_target']:
            resource_type['properties_target'] = payload['properties_target']

        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.create_entity(
            preexisting['_source'], "resource_types", resource_type)
        self.index_helper.save_document(preexisting['_source'],
                                        preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def delete_rs(self, event_type, payload, timestamp):
        id = payload['namespace']
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.delete_entity(
            preexisting['_source'], "resource_types", payload['name'], "name")
        self.index_helper.save_document(preexisting['_source'],
                                        preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def create_tag(self, event_type, payload, timestamp):
        id = payload['namespace']
        tag = {}
        tag['name'] = payload['name']
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.create_entity(preexisting['_source'], "tags", tag)
        self.index_helper.save_document(preexisting['_source'],
                                        preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def update_tag(self, event_type, payload, timestamp):
        id = payload['namespace']
        tag = {}
        tag['name'] = payload['name']
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.update_entity(
            preexisting['_source'], "tags", tag, payload['name_old'], "name")
        self.index_helper.save_document(preexisting['_source'],
                                        preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def delete_tag(self, event_type, payload, timestamp):
        id = payload['namespace']
        preexisting = self.index_helper.get_document(id, for_admin=True)
        self.delete_entity(
            preexisting['_source'], "tags", payload['name'], "name")
        self.index_helper.save_document(preexisting['_source'],
                                        preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def delete_props(self, event_type, payload, timestamp):
        return self.delete_field(
            event_type,
            payload,
            timestamp,
            'properties'
        )

    def delete_objects(self, event_type, payload, timestamp):
        return self.delete_field(
            event_type,
            payload,
            timestamp,
            'objects'
        )

    def delete_tags(self, event_type, payload, timestamp):
        return self.delete_field(
            event_type,
            payload,
            timestamp,
            'tags'
        )

    def delete_field(self, event_type, payload, timestamp, field):
        id = payload['namespace']
        preexisting = self.index_helper.get_document(id, for_admin=True)
        preexisting['_source'].pop(field, None)
        self.index_helper.save_document(preexisting['_source'],
                                        preexisting['_version'] + 1)
        return pipeline.IndexItem(self.index_helper.plugin,
                                  event_type,
                                  payload,
                                  preexisting['_source'])

    def format_namespace(self, payload):
        for key in self.namespace_delete_keys:
            if key in payload.keys():
                del payload[key]
        payload['id'] = payload['namespace']
        if 'display_name' in payload and payload['display_name']:
            payload['name'] = payload['display_name']
        else:
            payload['name'] = payload['namespace']
        return payload

    def format_object(self, payload):
        formatted_object = {}
        formatted_object['name'] = payload['name']
        formatted_object['description'] = payload['description']
        if payload['required']:
            formatted_object['required'] = payload['required']
        formatted_object['properties'] = []
        for property in payload['properties']:
            formatted_property = self.format_property(property)
            formatted_object['properties'].append(formatted_property)
        return formatted_object

    def format_property(self, payload):
        prop_data = {}
        for key, value in payload.items():
            if key not in self.property_delete_keys and value:
                prop_data[key] = value
        return prop_data

    def create_entity(self, doc, entity_name, entity_data):
        entity_list = doc.setdefault(entity_name, [])
        entity_list.append(entity_data)
        return doc

    def update_entity(self, doc, entity_name, entity_id, entity_data,
                      field_name):
        self.delete_entity(doc, entity_name, entity_id, field_name)
        self.create_entity(doc, entity_name, entity_data)
        return doc

    def delete_entity(self, doc, entity_name, entity_id, field_name):
        match_entity = None
        for index, item in enumerate(doc.get(entity_name, [])):
            if item[field_name] == entity_id:
                match_entity = index
                break
        if match_entity is not None:
            doc[entity_name].pop(match_entity)
        return doc
