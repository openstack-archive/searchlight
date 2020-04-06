# Copyright 2018 Verizon Wireless
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

import fixtures
from unittest import mock
import webob

from searchlight.common import wsgi
from searchlight import i18n
from searchlight.tests import utils as test_utils


class RequestTest(test_utils.BaseTestCase):

    def _set_expected_languages(self, all_locales=None, avail_locales=None):
        if all_locales is None:
            all_locales = []

        # Override localedata.locale_identifiers to return some locales.
        def returns_some_locales(*args, **kwargs):
            return all_locales

        self.useFixture(fixtures.MonkeyPatch(
            'babel.localedata.local_identifiers', returns_some_locales
        ))

        # Override gettext.find to return other than None for some languages.
        def fake_gettext_find(lang_id, *args, **kwargs):
            found_ret = '/glance/%s/LC_MESSAGES/glance.mo' % lang_id
            if avail_locales is None:
                # All locales are available.
                return found_ret
            languages = kwargs['languages']
            if languages[0] in avail_locales:
                return found_ret
            return None

        self.useFixture(fixtures.MonkeyPatch(
            'gettext.find', fake_gettext_find
        ))

    def test_language_accept_default(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept-Language"] = "zz-ZZ,zz;q=0.8"
        result = request.best_match_language()
        self.assertIsNone(result)

    def test_language_accept_none(self):
        request = wsgi.Request.blank('/tests/123')
        result = request.best_match_language()
        self.assertIsNone(result)

    def test_best_match_language_expected(self):
        # If Accept-Language is a supported language, best_match_language()
        # returns it.
        self._set_expected_languages(all_locales=['it'])

        req = wsgi.Request.blank('/', headers={'Accept-Language': 'it'})
        self.assertEqual('it', req.best_match_language())

    def test_request_match_language_unexpected(self):
        # If Accept-Language is a language we do not support,
        # best_match_language() returns None.
        self._set_expected_languages(all_locales=['it'])

        req = wsgi.Request.blank('/', headers={'Accept-Language': 'unknown'})
        self.assertIsNone(req.best_match_language())

    def test_best_match_language_unknown(self):
        # Test that we are actually invoking language negotiation by webob
        request = wsgi.Request.blank('/')
        accepted = 'unknown-lang'
        request.headers = {'Accept-Language': accepted}

        # TODO(rosmaita): simplify when lower_constraints has webob >= 1.8.1
        try:
            from webob.acceptparse import AcceptLanguageValidHeader  # noqa
            cls = webob.acceptparse.AcceptLanguageValidHeader
            funcname = 'lookup'
            # Bug #1765748: see comment in code in the function under test
            # to understand why this is the correct return value for the
            # webob 1.8.x mock
            retval = 'fake_LANG'
        except ImportError:
            cls = webob.acceptparse.AcceptLanguage
            funcname = 'best_match'
            retval = None

        with mock.patch.object(cls, funcname) as mocked_function:
            mocked_function.return_value = retval

            self.assertIsNone(request.best_match_language())
            mocked_function.assert_called_once()

        # If Accept-Language is missing or empty, match should be None
        request.headers = {'Accept-Language': ''}
        self.assertIsNone(request.best_match_language())
        request.headers.pop('Accept-Language')
        self.assertIsNone(request.best_match_language())


class ResourceTest(test_utils.BaseTestCase):

    @mock.patch.object(wsgi, 'translate_exception')
    def test_resource_call_error_handle_localized(self,
                                                  mock_translate_exception):
        class Controller(object):
            def delete(self, req, identity):
                raise webob.exc.HTTPBadRequest(explanation='Not Found')

        actions = {'action': 'delete', 'identity': 12}
        env = {'wsgiorg.routing_args': [None, actions]}
        request = wsgi.Request.blank('/tests/123', environ=env)
        message_es = 'No Encontrado'

        resource = wsgi.Resource(Controller(),
                                 wsgi.JSONRequestDeserializer(),
                                 None)
        translated_exc = webob.exc.HTTPBadRequest(message_es)
        mock_translate_exception.return_value = translated_exc

        e = self.assertRaises(webob.exc.HTTPBadRequest,
                              resource, request)
        self.assertEqual(message_es, str(e))

    @mock.patch.object(i18n, 'translate')
    def test_translate_exception(self, mock_translate):
        # TODO(rosmaita): simplify when lower_constraints has webob >= 1.8.1
        try:
            from webob.acceptparse import AcceptLanguageValidHeader  # noqa
            cls = webob.acceptparse.AcceptLanguageValidHeader
            funcname = 'lookup'
        except ImportError:
            cls = webob.acceptparse.AcceptLanguage
            funcname = 'best_match'

        with mock.patch.object(cls, funcname) as mocked_function:
            mock_translate.return_value = 'No Encontrado'
            mocked_function.return_value = 'de'

            req = wsgi.Request.blank('/tests/123')
            req.headers["Accept-Language"] = "de"

            e = webob.exc.HTTPNotFound(explanation='Not Found')
            e = wsgi.translate_exception(req, e)
            self.assertEqual('No Encontrado', e.explanation)
