"""Printing a filled form **writes** (CLAUDE.md §4.4).

`GET /api/admissions/<id>/form/?mode=filled` allocates a gapless form number
under a lock and inserts a `PrintedForm`. It is a plain `APIView`, so the
permission layer priced it by HTTP method — `documents.view` — and a read-only
account could loop the URL and exhaust the institution's numbered series.
A blank form records nothing and stays a read.
"""

from django.test import TestCase, override_settings

from forms.models import PrintedForm

from . import factories as f
from .test_api import client_for


@override_settings(ROOT_URLCONF='forms.tests.urls')
class FormPrintPermissionTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        self.reader = f.make_user(
            self.world['branch'], phone='01711000044',
            permissions=['documents.view', 'admissions.view'],
        )

    def path(self, mode):
        return (f'/api/admissions/{self.world["admission"].pk}/form/?mode={mode}')

    def test_a_reader_cannot_print_a_filled_form(self):
        response = client_for(self.reader).get(self.path('filled'))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PrintedForm.objects.exists())

    def test_a_reader_may_still_print_a_blank(self):
        """Blank issues no number, so it stays what the catalogue calls a read."""
        response = client_for(self.reader).get(self.path('blank'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PrintedForm.objects.exists())

    def test_an_officer_who_may_upload_documents_prints_and_gets_a_number(self):
        officer = f.make_user(
            self.world['branch'], phone='01711000045',
            permissions=['documents.view', 'documents.upload', 'admissions.view'],
        )

        response = client_for(officer).get(self.path('filled'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PrintedForm.objects.count(), 1)
