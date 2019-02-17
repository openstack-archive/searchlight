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

from oslo_serialization import jsonutils

from searchlight.tests.functional import generate_load_data


class FakeImage(dict):

    def __init__(self, **kwargs):
        super(FakeImage, self).__init__(**kwargs)


class FakeImageMember(dict):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            self.__setitem__(key, value)


class FakeImages(object):
    def __init__(self, images_list):
        self.images = images_list

    def list(self):
        return self.images

    def get(self, imageid):
        for image in self.images:
            if image['id'] == imageid:
                return image
        return None


class FakeImageMembers(object):

    def __init__(self, images_members):
        self.image_members = images_members

    def list(self, image_id):
        if image_id in self.image_members:
            return self.image_members[image_id]
        else:
            return []


class FakeNamespace(dict):

    def __init__(self, **kwargs):
        super(FakeNamespace, self).__init__(**kwargs)

        # Actual glance client doesn't return all the fields while listing the
        # namespaces. Simulate the similar behaviour by keeping a copy of the
        # field as private for future retrieval during individual get() on
        # a single namespace
        if "tags" in self:
            self.__setitem__('_tags', self.__getitem__("tags"))
        if "properties" in self:
            self.__setitem__('_properties', self.__getitem__("properties"))
        if "objects" in self:
            self.__setitem__('_objects', self.__getitem__("objects"))

        for field in ("tags", "objects", "properties"):
            if field in self:
                self.__delitem__(field)


class FakeNamespaces(object):
    def __init__(self, namespaces_list):
        self.namespaces = namespaces_list

    def list(self):
        return self.namespaces

    def get(self, namespace_name):
        for namespace in self.namespaces:
            if namespace['namespace'] == namespace_name:
                new_namespace = namespace.copy()
                if "_tags" in new_namespace:
                    new_namespace["tags"] = new_namespace["_tags"]
                if "_objects" in new_namespace:
                    new_namespace["objects"] = new_namespace["_objects"]
                if "_properties" in new_namespace:
                    new_namespace["properties"] = new_namespace["_properties"]

                for field in ("_tags", "_objects", "_properties"):
                    if field in new_namespace:
                        new_namespace.__delitem__(field)
                return new_namespace
        return None


class FakeGlanceClient(object):

    def __init__(self):
        # Load Images from file
        self._images = []
        with open(generate_load_data.IMAGES_FILE, "r+b") as file:
            image_data = jsonutils.load(file)
        for image in image_data:
            fake_image = FakeImage(**image)
            self._images.append(fake_image)
        self.images = FakeImages(self._images)

        # Load Images members from file
        self._images_members_dict = dict()
        self._image_members_list = []
        with open(generate_load_data.IMAGE_MEMBERS_FILE, "r+b") as file:
            image_members_data = jsonutils.load(file)
        for image_id, image_members in image_members_data.items():
            for image_member in image_members:
                fake_image_member = FakeImageMember(**image_member)
                self._image_members_list.append(fake_image_member)
            self._images_members_dict[image_id] = self._image_members_list
        self.image_members = FakeImageMembers(self._images_members_dict)

        # Load Metadef namespaces from file
        self._metadefs_namespace = []
        self.metadefs_namespace = []
        with open(generate_load_data.METADEFS_FILE, "r+b") as file:
            metadefs_namespace_data = jsonutils.load(file)
        for metadef_namespace in metadefs_namespace_data:
            fake_namespace = FakeNamespace(**metadef_namespace)
            self._metadefs_namespace.append(fake_namespace)
        self.metadefs_namespace = FakeNamespaces(self._metadefs_namespace)


def get_fake_glance_client():
    return FakeGlanceClient()
