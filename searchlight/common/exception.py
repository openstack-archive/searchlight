# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""Searchlight exception subclasses"""


from searchlight.i18n import _

_FATAL_EXCEPTION_FORMAT_ERRORS = False


class SearchlightException(Exception):
    """
    Base Searchlight Exception

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.
    """
    message = _("An unknown exception occurred")

    def __init__(self, message=None, *args, **kwargs):
        if not message:
            message = self.message
        try:
            if kwargs:
                message = message % kwargs
        except Exception:
            if _FATAL_EXCEPTION_FORMAT_ERRORS:
                raise
            else:
                # at least get the core message out if something happened
                pass
        self.msg = message
        super(SearchlightException, self).__init__(message)

    def __unicode__(self):
        # NOTE(flwang): By default, self.msg is an instance of Message, which
        # can't be converted by str(). Based on the definition of
        # __unicode__, it should return unicode always.
        return str(self.msg)


class NotFound(SearchlightException):
    message = _("An object with the specified identifier was not found.")


class Duplicate(SearchlightException):
    message = _("An object with the same identifier already exists.")


class Forbidden(SearchlightException):
    message = _("You are not authorized to complete this action.")


class Invalid(SearchlightException):
    message = _("Data supplied was not valid.")


class InvalidPropertyProtectionConfiguration(Invalid):
    message = _("Invalid configuration in property protection file.")


class ReservedProperty(Forbidden):
    message = _("Attribute '%(property)s' is reserved.")


class InvalidContentType(SearchlightException):
    message = _("Invalid content type %(content_type)s")


class WorkerCreationFailure(SearchlightException):
    message = _("Server worker creation failed: %(reason)s.")


class SchemaLoadError(SearchlightException):
    message = _("Unable to load schema: %(reason)s")


class InvalidObject(SearchlightException):
    message = _("Provided object does not match schema "
                "'%(schema)s': %(reason)s")


class SIGHUPInterrupt(SearchlightException):
    message = _("System SIGHUP signal received.")


class JsonPatchException(SearchlightException):
    message = _("Invalid jsonpatch request")


class InvalidJsonPatchBody(JsonPatchException):
    message = _("The provided body %(body)s is invalid "
                "under given schema: %(schema)s")


class InvalidJsonPatchPath(JsonPatchException):
    message = _("The provided path '%(path)s' is invalid: %(explanation)s")

    def __init__(self, message=None, *args, **kwargs):
        self.explanation = kwargs.get("explanation")
        super(InvalidJsonPatchPath, self).__init__(message, *args, **kwargs)


class IndexingException(SearchlightException):
    message = _("An error occurred during index creation or initial loading")


class InvalidAPIVersionProvided(SearchlightException):
    message = _("The provided API version is not supported, "
                "the current available version range for %(service)s "
                "is: from %(min_version)s to %(max_version)s.")


class VersionedNotificationMismatch(SearchlightException):
    message = _("Provided notification version "
                "%(provided_maj)s.%(provided_min)s did not match expected "
                "%(expected_maj)s.%(expected_min)s for %(type)s")
