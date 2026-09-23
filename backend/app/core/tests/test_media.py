"""The production /media fallback (core/media.py).

documents/ holds birth certificates. The only way out for one is the
authenticated download, so every spelling that reaches it here must 404.
"""

import os
import tempfile

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.media import serve_media


class ServeMediaTests(SimpleTestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for rel, body in [('students/photos/p1.jpg', b'photo'),
                          ('documents/2026/09/birth.pdf', b'secret')]:
            full = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb') as fh:
                fh.write(body)
        self.request = RequestFactory().get('/media/x')

    def get(self, path):
        with override_settings(MEDIA_ROOT=self.root):
            return serve_media(self.request, path)

    def test_a_photo_is_served(self):
        response = self.get('students/photos/p1.jpg')
        self.assertEqual(b''.join(response.streaming_content), b'photo')

    def test_a_document_is_refused(self):
        with self.assertRaises(Http404):
            self.get('documents/2026/09/birth.pdf')

    def test_a_document_is_refused_by_any_route_that_resolves_to_it(self):
        """The pattern-only version of this served these three."""
        for path in ['students/../documents/2026/09/birth.pdf',
                     './documents/2026/09/birth.pdf',
                     'students/photos/../../documents/2026/09/birth.pdf',
                     'students\\..\\documents/2026/09/birth.pdf',
                     'documents']:
            with self.subTest(path=path), self.assertRaises(Http404):
                self.get(path)

    def test_nothing_outside_media_root_is_reachable(self):
        for path in ['../settings.py', 'students/../../etc/passwd']:
            with self.subTest(path=path), self.assertRaises(Http404):
                self.get(path)
