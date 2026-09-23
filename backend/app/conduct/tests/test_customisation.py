"""Two reports, one question bank — and who is meant to fill them.

The section alone could not answer "some reports have fewer questions, some
more": a question belongs to exactly one section, so two templates drawing on
`conduct` asked an identical list and the only way to differ was to duplicate
নামাজ into a second section — two rows that then drift apart.

So an explicit selection overrides the section, which is the same shape as
every default on the SPA. And responsibility is a row of its own, because
"whose sheet is this?" is a question nobody could answer before.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from conduct.models import (ReportAssignment, ReportTemplate,
                            ReportTemplateQuestion)
from conduct.services import (responsible_teachers, set_template_questions,
                              sheet, template_questions)
from staff.services import create_teacher

from .test_conduct import ConductFixture, make_question


class ChoosingQuestionsTests(ConductFixture, TestCase):
    def setUp(self):
        self.build()
        self.daily = self.template
        self.monthly = ReportTemplate.objects.create(
            branch=self.branch, name='Monthly review', name_bn='মাসিক পর্যালোচনা',
            frequency='monthly', section='conduct')

    def test_a_template_with_no_choice_asks_its_whole_section(self):
        """The quick path stays quick: most institutions want the section."""
        self.assertEqual(len(template_questions(self.daily)), 3)

    def test_two_templates_can_ask_different_questions_from_one_bank(self):
        """The thing that was impossible: fewer questions on one, more on the
        other, and নামাজ shared rather than copied."""
        set_template_questions(self.daily, [self.salah.pk])
        set_template_questions(self.monthly,
                               [self.salah.pk, self.quran.pk, self.paras.pk])

        self.assertEqual([q.pk for q in template_questions(self.daily)],
                         [self.salah.pk])
        self.assertEqual(len(template_questions(self.monthly)), 3)
        # One question, two templates, one row in the bank.
        self.assertEqual(self.salah.report_links.count(), 2)

    def test_the_order_given_is_the_order_asked(self):
        set_template_questions(self.daily,
                               [self.paras.pk, self.salah.pk, self.quran.pk])

        self.assertEqual([q.pk for q in template_questions(self.daily)],
                         [self.paras.pk, self.salah.pk, self.quran.pk])

    def test_setting_the_list_again_replaces_it(self):
        set_template_questions(self.daily, [self.salah.pk, self.quran.pk])
        set_template_questions(self.daily, [self.quran.pk])

        self.assertEqual([q.pk for q in template_questions(self.daily)],
                         [self.quran.pk])
        self.assertEqual(ReportTemplateQuestion.objects.filter(
            template=self.daily).count(), 1)

    def test_an_empty_list_puts_the_template_back_on_its_section(self):
        set_template_questions(self.daily, [self.salah.pk])
        set_template_questions(self.daily, [])

        self.assertEqual(len(template_questions(self.daily)), 3)

    def test_a_deactivated_question_drops_out_even_when_chosen(self):
        set_template_questions(self.daily, [self.salah.pk, self.quran.pk])
        self.quran.is_active = False
        self.quran.save(update_fields=['is_active'])

        self.assertEqual([q.pk for q in template_questions(self.daily)],
                         [self.salah.pk])

    def test_a_question_may_come_from_any_section_of_the_bank(self):
        """The section is where a template looks by default, not a fence: a
        report may ask a question that lives with the admission form's."""
        elsewhere = make_question(self.branch, text='Previous madrasah',
                                  text_bn='পূর্বের মাদ্রাসা', section='admission')

        set_template_questions(self.daily, [self.salah.pk, elsewhere.pk])

        self.assertIn(elsewhere, template_questions(self.daily))

    def test_another_institutions_question_is_silently_not_added(self):
        from branches.models import InstitutionType
        from branches.services import create_branch

        other = create_branch(name='Chittagong', code='CTG',
                              institution_type=InstitutionType.MADRASAH)
        theirs = make_question(other, text='Theirs', section='conduct')

        set_template_questions(self.daily, [self.salah.pk, theirs.pk])

        self.assertEqual([q.pk for q in template_questions(self.daily)],
                         [self.salah.pk])


class ResponsibilityTests(ConductFixture, TestCase):
    def setUp(self):
        self.build()
        self.teacher = create_teacher(branch=self.branch, name='Abdul Karim')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_the_sheet_says_who_is_meant_to_fill_it(self):
        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, teacher=self.teacher)

        data = sheet(self.template, academic_class=self.academic_class)

        self.assertEqual([row['name'] for row in data['responsible']],
                         ['Abdul Karim'])

    def test_a_whole_class_assignment_covers_every_section(self):
        from academics.models import Section

        section = Section.objects.create(branch=self.branch,
                                         academic_class=self.academic_class, name='A')
        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, teacher=self.teacher)

        rows = responsible_teachers(self.template, self.academic_class, section)

        self.assertEqual([row.teacher_id for row in rows], [self.teacher.pk])

    def test_responsibility_does_not_fence_a_colleague_out(self):
        """A sheet locked to one person is a sheet nobody fills the day they
        are ill. `filled_by` records who actually did it."""
        from conduct.services import save_sheet

        other = create_teacher(branch=self.branch, name='Cover Teacher')
        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, teacher=self.teacher)

        result = save_sheet(template=self.template,
                            academic_class=self.academic_class,
                            rows=[{'enrolment': self.enrolments[0].pk,
                                   'answers': {str(self.salah.pk): True}}],
                            teacher=other, actor=self.user)

        self.assertEqual(result['saved'], 1)
        from conduct.models import StudentReport
        self.assertEqual(StudentReport.objects.get().filled_by_id, other.pk)

    def test_one_teacher_cannot_be_given_the_same_class_twice(self):
        from django.db import IntegrityError, transaction

        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, teacher=self.teacher)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReportAssignment.objects.create(
                    branch=self.branch, template=self.template,
                    academic_class=self.academic_class, teacher=self.teacher)


class CustomisationApiTests(ConductFixture, TestCase):
    def setUp(self):
        self.build()
        self.teacher = create_teacher(branch=self.branch, name='Abdul Karim')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_setting_a_templates_questions_through_the_api(self):
        response = self.client.post(
            f'/api/report-templates/{self.template.pk}/questions/',
            {'questions': [self.quran.pk, self.salah.pk]}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.data['items']],
                         [self.quran.pk, self.salah.pk])
        self.assertEqual(response.data['item_count'], 2)

    def test_choosing_questions_is_a_settings_act(self):
        """A teacher fills the sheet; deciding what is on it is the office's."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        teacher_user = User.objects.create_user(
            phone='01711000077', password='pass-phrase-1234', name='Teacher',
            branch=self.branch, user_type='teacher',
            permissions=['conduct.view', 'conduct.take'])

        client = APIClient()
        client.force_authenticate(teacher_user)
        response = client.post(
            f'/api/report-templates/{self.template.pk}/questions/',
            {'questions': [self.salah.pk]}, format='json')

        self.assertEqual(response.status_code, 403)

    def test_handing_out_responsibility_through_the_api(self):
        response = self.client.post('/api/report-assignments/', {
            'template': self.template.pk,
            'academic_class': self.academic_class.pk,
            'teacher': self.teacher.pk,
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ReportAssignment.objects.get().teacher_id, self.teacher.pk)

    def test_a_teacher_may_read_who_is_responsible(self):
        """Both a teacher and a principal ask "whose sheet is this?"."""
        from django.contrib.auth import get_user_model

        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, teacher=self.teacher)

        User = get_user_model()
        teacher_user = User.objects.create_user(
            phone='01711000088', password='pass-phrase-1234', name='Teacher',
            branch=self.branch, user_type='teacher',
            permissions=['conduct.view'])
        client = APIClient()
        client.force_authenticate(teacher_user)

        response = client.get('/api/report-assignments/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)

    def test_a_section_of_another_class_is_refused(self):
        from academics.models import AcademicClass, Section

        other_class = AcademicClass.objects.create(
            branch=self.branch, session=self.session, stream=self.stream,
            name='Class 9', year=2026)
        their_section = Section.objects.create(
            branch=self.branch, academic_class=other_class, name='A')

        response = self.client.post('/api/report-assignments/', {
            'template': self.template.pk,
            'academic_class': self.academic_class.pk,
            'section': their_section.pk,
            'teacher': self.teacher.pk,
        }, format='json')

        self.assertEqual(response.status_code, 400)

    def test_another_institutions_assignment_is_404(self):
        from branches.models import InstitutionType, Session
        from branches.services import create_branch
        from academics.models import AcademicClass
        from datetime import date

        other = create_branch(name='Chittagong', code='CTG',
                              institution_type=InstitutionType.MADRASAH)
        other_session = Session.objects.create(
            branch=other, name='2026', starts_on=date(2026, 1, 1),
            ends_on=date(2026, 12, 31))
        their_class = AcademicClass.objects.create(
            branch=other, session=other_session, stream=other.stream_set.first(),
            name='Class 5', year=2026)
        their_template = ReportTemplate.objects.create(
            branch=other, name='Theirs', section='conduct')
        their_row = ReportAssignment.objects.create(
            branch=other, template=their_template, academic_class=their_class,
            teacher=create_teacher(branch=other, name='Their Teacher'))

        response = self.client.get(f'/api/report-assignments/{their_row.pk}/')

        self.assertEqual(response.status_code, 404)
