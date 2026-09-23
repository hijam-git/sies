"""A teacher's own sheets — what their dashboard lists (conduct.services.duties_for).

Responsibility is set on Settings → Reports (`ReportAssignment`). These tests
are about the other end of it: the named teacher being told, on their own
screen, what is theirs to fill and how much of it is done.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from conduct.models import ReportAssignment, ReportFrequency, ReportTemplate
from conduct.services import duties_for, save_sheet
from staff.services import create_teacher

from .test_conduct import ConductFixture

DAY = date(2026, 9, 23)


class DutiesTests(ConductFixture, TestCase):
    def setUp(self):
        self.build()
        self.teacher = create_teacher(branch=self.branch, name='Abdul Karim')
        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, teacher=self.teacher)

    def fill(self, enrolments, on_date=DAY):
        save_sheet(template=self.template, academic_class=self.academic_class,
                   period=on_date.isoformat(),
                   rows=[{'enrolment': e.pk, 'answers': {str(self.salah.pk): True}}
                         for e in enrolments],
                   teacher=self.teacher, actor=self.user)

    def test_an_assigned_sheet_is_on_the_teachers_list(self):
        [duty] = duties_for(self.teacher, branch=self.branch, on_date=DAY)

        self.assertEqual(duty['template'], self.template.pk)
        self.assertEqual(duty['academic_class'], self.academic_class.pk)
        self.assertEqual(duty['period'], '2026-09-23')
        self.assertEqual((duty['filled_count'], duty['student_count']), (0, 3))
        self.assertFalse(duty['is_done'])

    def test_progress_counts_the_students_already_filled(self):
        self.fill(self.enrolments[:2])

        [duty] = duties_for(self.teacher, branch=self.branch, on_date=DAY)

        self.assertEqual(duty['filled_count'], 2)
        self.assertFalse(duty['is_done'])

    def test_a_whole_sheet_is_done_and_tomorrow_starts_again(self):
        """A daily sheet is today's job: yesterday's full sheet does not count."""
        self.fill(self.enrolments)

        [today] = duties_for(self.teacher, branch=self.branch, on_date=DAY)
        [tomorrow] = duties_for(self.teacher, branch=self.branch,
                                on_date=date(2026, 9, 24))

        self.assertTrue(today['is_done'])
        self.assertEqual(tomorrow['filled_count'], 0)

    def test_a_weekly_sheet_is_the_same_job_all_week(self):
        self.template.frequency = ReportFrequency.WEEKLY
        self.template.save()

        monday = duties_for(self.teacher, on_date=date(2026, 9, 21))[0]
        sunday = duties_for(self.teacher, on_date=date(2026, 9, 27))[0]

        self.assertEqual(monday['period'], '2026-W39')
        self.assertEqual(sunday['period'], monday['period'])

    def test_a_section_assignment_counts_only_that_section(self):
        from academics.models import Section

        section = Section.objects.create(branch=self.branch,
                                         academic_class=self.academic_class, name='A')
        self.enrolments[0].section = section
        self.enrolments[0].save()
        ReportAssignment.objects.all().delete()
        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, section=section, teacher=self.teacher)

        [duty] = duties_for(self.teacher, on_date=DAY)

        self.assertEqual((duty['section'], duty['section_name']), (section.pk, 'A'))
        self.assertEqual(duty['student_count'], 1)

    def test_another_teachers_sheet_is_not_on_this_list(self):
        colleague = create_teacher(branch=self.branch, name='Cover Teacher')

        self.assertEqual(duties_for(colleague, on_date=DAY), [])

    def test_a_retired_template_or_last_years_class_drops_off(self):
        """A list that never empties is a list nobody reads."""
        self.template.is_active = False
        self.template.save()
        self.assertEqual(duties_for(self.teacher, on_date=DAY), [])

        self.template.is_active = True
        self.template.save()
        self.session.is_current = False
        self.session.save()
        self.assertEqual(duties_for(self.teacher, on_date=DAY), [])

    def test_what_is_left_to_do_comes_first(self):
        done = ReportTemplate.objects.create(
            branch=self.branch, name='A done one', frequency=ReportFrequency.DAILY,
            section='conduct')
        ReportAssignment.objects.create(
            branch=self.branch, template=done,
            academic_class=self.academic_class, teacher=self.teacher)
        save_sheet(template=done, academic_class=self.academic_class,
                   period=DAY.isoformat(),
                   rows=[{'enrolment': e.pk, 'answers': {str(self.salah.pk): True}}
                         for e in self.enrolments],
                   teacher=self.teacher, actor=self.user)

        duties = duties_for(self.teacher, on_date=DAY)

        self.assertEqual([d['is_done'] for d in duties], [False, True])

    def test_no_teacher_profile_means_no_duties(self):
        self.assertEqual(duties_for(None, on_date=DAY), [])


class MyDutiesApiTests(ConductFixture, TestCase):
    URL = '/api/conduct/my-duties/'

    def setUp(self):
        self.build()
        User = get_user_model()
        self.teacher_user = User.objects.create_user(
            phone='01711000055', password='pass-phrase-1234', name='Abdul Karim',
            branch=self.branch, user_type='teacher',
            permissions=['conduct.view', 'conduct.take'])
        self.teacher = create_teacher(branch=self.branch, name='Abdul Karim',
                                      user=self.teacher_user)
        ReportAssignment.objects.create(
            branch=self.branch, template=self.template,
            academic_class=self.academic_class, teacher=self.teacher)

    def get(self, user, query=''):
        client = APIClient()
        client.force_authenticate(user)
        return client.get(self.URL + query)

    def test_the_teacher_gets_their_own_sheets(self):
        response = self.get(self.teacher_user, '?date=2026-09-23')

        self.assertEqual(response.status_code, 200)
        [duty] = response.data['duties']
        self.assertEqual(duty['template_name_bn'], 'দৈনিক আমল')
        self.assertEqual(duty['period'], '2026-09-23')

    def test_a_principal_with_no_assignments_gets_an_empty_list(self):
        """About *your* duties — not everybody's, and not a 403."""
        response = self.get(self.user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['duties'], [])

    def test_it_needs_conduct_view(self):
        User = get_user_model()
        clerk = User.objects.create_user(
            phone='01711000066', password='pass-phrase-1234', name='Clerk',
            branch=self.branch, user_type='employee', permissions=['fees.view'])

        self.assertEqual(self.get(clerk).status_code, 403)

    def test_a_bad_date_is_a_400(self):
        self.assertEqual(self.get(self.teacher_user, '?date=yesterday').status_code, 400)
