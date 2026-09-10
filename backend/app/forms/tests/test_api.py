"""The forms API: branch isolation, and the print endpoint's two modes.

Every account holds the full permission list, so a refusal here proves the
*branch scope* refused it and not a missing checkbox.
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from forms.models import FormTemplate

from . import factories as f


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@override_settings(ROOT_URLCONF='forms.tests.urls')
class AdmissionFormEndpointTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        self.client_ = client_for(self.world['user'])

    def test_the_endpoint_returns_a_print_ready_html_document(self):
        response = self.client_.get(f'/api/admissions/{self.world["admission"].pk}/form/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/html'))
        body = response.content.decode()
        self.assertIn('<!DOCTYPE html>', body)
        self.assertIn('রহিম উদ্দিন', body)

    def test_blank_mode_renders_the_same_document_with_empty_rules(self):
        response = self.client_.get(
            f'/api/admissions/{self.world["admission"].pk}/form/?mode=blank',
        )
        body = response.content.decode()
        self.assertIn('বিনীত নিবেদন', body)
        self.assertNotIn('রহিম উদ্দিন', body)

    def test_an_unknown_template_is_404(self):
        response = self.client_.get(
            f'/api/admissions/{self.world["admission"].pk}/form/?template=999999',
        )
        self.assertEqual(response.status_code, 404)


@override_settings(ROOT_URLCONF='forms.tests.urls')
class BranchIsolationTests(TestCase):
    """Another institution's row is **404, not 403** (CLAUDE.md §5).

    403 confirms it exists, which is what a probe is looking for.
    """

    def setUp(self):
        self.dhaka = f.small_world(code='DHK', phone='01711000001')
        self.ctg = f.small_world(code='CTG', phone='01722000001')

    def test_another_branchs_admission_form_is_404(self):
        response = client_for(self.dhaka['user']).get(
            f'/api/admissions/{self.ctg["admission"].pk}/form/',
        )
        self.assertEqual(response.status_code, 404)

    def test_another_branchs_template_is_404(self):
        response = client_for(self.dhaka['user']).get(
            f'/api/form-templates/{self.ctg["template"].pk}/',
        )
        self.assertEqual(response.status_code, 404)

    def test_the_template_list_shows_only_this_institutions_templates(self):
        response = client_for(self.dhaka['user']).get('/api/form-templates/')
        ids = {row['id'] for row in response.json()['results']}
        self.assertEqual(ids, {self.dhaka['template'].pk})


@override_settings(ROOT_URLCONF='forms.tests.urls')
class TemplateApiValidationTests(TestCase):
    """The editor gets a 400 naming the bad block, not a 500."""

    def setUp(self):
        self.world = f.small_world()
        self.client_ = client_for(self.world['user'])

    def test_an_unknown_placeholder_is_a_400(self):
        response = self.client_.post('/api/form-templates/', {
            'name': 'Broken', 'form_type': 'admission',
            'blocks': [{'type': 'prose', 'text': '{{student.nam}}'}],
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FormTemplate.objects.filter(name='Broken').exists())

    def test_a_malformed_block_is_a_400(self):
        response = self.client_.post('/api/form-templates/', {
            'name': 'Broken', 'form_type': 'admission',
            'blocks': [{'type': 'nope'}],
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_a_valid_template_is_created(self):
        response = self.client_.post('/api/form-templates/', {
            'name': 'Transfer form', 'form_type': 'certificate',
            'blocks': [{'type': 'prose', 'text': 'আমি {{student.name_bn}}'}],
        }, format='json')
        self.assertEqual(response.status_code, 201)

    def test_the_placeholder_picker_is_served_with_the_template(self):
        """The editor's list and the validator's list are the same list."""
        response = self.client_.get(f'/api/form-templates/{self.world["template"].pk}/')
        groups = response.json()['placeholder_groups']
        names = {name for group in groups.values() for name in group}
        self.assertIn('student.name_bn', names)


@override_settings(ROOT_URLCONF='forms.tests.urls')
class AnswersEndpointTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        self.student = f.make_student(self.world['branch'])
        self.admission = self.world['admission']
        self.admission.student = self.student
        self.admission.status = 'admitted'
        self.admission.save(update_fields=['student', 'status'])

    def test_posting_answers_applies_the_maps_to_rule(self):
        from forms.models import AdmissionAnswer, Question

        mapped = Question.objects.get(maps_to='previous_institution')
        free = f.make_question(self.world['branch'])

        response = client_for(self.world['user']).post(
            f'/api/admissions/{self.admission.pk}/answers/',
            {'answers': {str(mapped.pk): 'Dasherbari', str(free.pk): 'না'}},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'stored': 1, 'mapped': 1})

        self.student.refresh_from_db()
        self.assertEqual(self.student.previous_institution, 'Dasherbari')
        self.assertEqual(AdmissionAnswer.objects.count(), 1)
