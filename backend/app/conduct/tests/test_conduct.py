"""The observation register: the sheet, the save, and who may fill it.

The properties are the attendance register's, because it is the same act:

1. the sheet is the CLASS's students, in roll order — not whoever the payload
   names;
2. saving is idempotent, so two teachers with the same class open on two phones
   produce one sheet, not two;
3. a value that does not fit its question becomes unanswered rather than
   failing forty students' save;
4. a teacher fills their own classes and nobody else's, and another
   institution's class is 404.
"""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from academics.models import Enrolment
from conduct.models import (ReportAnswer, ReportFrequency, ReportTemplate,
                            StudentReport)
from conduct.services import period_for, save_sheet, sheet, template_questions
from forms.models import Question, QuestionType
from students.models import Student
from students.services import allocate_student_id


def make_question(branch, *, text, text_bn='', type=QuestionType.YES_NO,
                  options=None, order=0, section='conduct'):
    return Question.objects.create(
        branch=branch, section=section, type=type, text=text,
        text_bn=text_bn or text, options=options or [], order=order,
    )


class ConductFixture:
    """One institution, one class, three students, and a daily sheet."""

    def build(self):
        from branches.models import InstitutionType, Session
        from branches.services import create_branch
        from academics.models import AcademicClass
        from academics.services import enrol_student
        from django.contrib.auth import get_user_model

        self.branch = create_branch(name='Dhaka Madrasah', name_bn='ঢাকা মাদ্রাসা',
                                    code='DHK',
                                    institution_type=InstitutionType.MADRASAH)
        self.session = Session.objects.create(
            branch=self.branch, name='2026', starts_on=date(2026, 1, 1),
            ends_on=date(2026, 12, 31), is_current=True)
        self.session.streams.set(self.branch.stream_set.all())
        self.stream = self.branch.stream_set.first()
        self.academic_class = AcademicClass.objects.create(
            branch=self.branch, session=self.session, stream=self.stream,
            name='Class 5', year=2026)

        self.enrolments = []
        for index, name in enumerate(['Abdullah', 'Bilal', 'Umar'], start=1):
            student = Student.objects.create(
                branch=self.branch, stream=self.stream,
                student_id=allocate_student_id(), name=name,
                admitted_on=date(2026, 1, 5))
            self.enrolments.append(enrol_student(
                branch=self.branch, student=student, session=self.session,
                academic_class=self.academic_class, roll=index,
                enrolled_on=date(2026, 1, 5)))

        self.salah = make_question(self.branch, text='Salah', text_bn='নামাজ', order=10)
        self.quran = make_question(
            self.branch, text='Quran', text_bn='তিলাওয়াত',
            type=QuestionType.SINGLE_CHOICE, order=20,
            options=[{'value': 'good', 'label': 'ভালো'},
                     {'value': 'fair', 'label': 'মোটামুটি'},
                     {'value': 'weak', 'label': 'দুর্বল'}])
        self.paras = make_question(self.branch, text='Paras', text_bn='কত পারা',
                                   type=QuestionType.NUMBER, order=30)

        self.template = ReportTemplate.objects.create(
            branch=self.branch, name='Daily amal', name_bn='দৈনিক আমল',
            frequency=ReportFrequency.DAILY, section='conduct')

        User = get_user_model()
        from accounts.permissions import VALID_PERMISSIONS
        self.user = User.objects.create_user(
            phone='01711000001', password='pass-phrase-1234', name='Principal',
            branch=self.branch, user_type='principal',
            permissions=sorted(VALID_PERMISSIONS))


class SheetTests(ConductFixture, TestCase):
    def setUp(self):
        self.build()

    def test_the_sheet_is_this_classs_students_in_roll_order(self):
        data = sheet(self.template, academic_class=self.academic_class,
                     on_date=date(2026, 9, 23))

        self.assertEqual([row['roll'] for row in data['students']], [1, 2, 3])
        self.assertEqual(data['period'], '2026-09-23')

    def test_the_questions_come_from_the_bank_in_their_own_order(self):
        """There is no second question model — Settings → Questions is it."""
        data = sheet(self.template, academic_class=self.academic_class)

        self.assertEqual([item['text_bn'] for item in data['items']],
                         ['নামাজ', 'তিলাওয়াত', 'কত পারা'])

    def test_a_question_in_another_section_is_not_on_this_sheet(self):
        """The admission form's questions and the আমল sheet share one bank; the
        section is what keeps them apart."""
        make_question(self.branch, text='Previous madrasah', section='admission')

        self.assertEqual(len(template_questions(self.template)), 3)

    def test_a_deactivated_question_leaves_tomorrows_sheet_alone(self):
        self.quran.is_active = False
        self.quran.save(update_fields=['is_active'])

        data = sheet(self.template, academic_class=self.academic_class)

        self.assertNotIn('তিলাওয়াত', [item['text_bn'] for item in data['items']])


class SaveTests(ConductFixture, TestCase):
    def setUp(self):
        self.build()
        self.day = date(2026, 9, 23)

    def rows(self, **answers):
        return [{'enrolment': self.enrolments[0].pk, 'answers': answers}]

    def test_one_save_writes_one_sheet_per_student(self):
        result = save_sheet(
            template=self.template, academic_class=self.academic_class,
            on_date=self.day, actor=self.user,
            rows=[{'enrolment': e.pk,
                   'answers': {str(self.salah.pk): True,
                               str(self.quran.pk): 'good',
                               str(self.paras.pk): 12}}
                  for e in self.enrolments])

        self.assertEqual(result['saved'], 3)
        self.assertEqual(StudentReport.objects.count(), 3)
        self.assertEqual(ReportAnswer.objects.count(), 9)

    def test_saving_twice_writes_the_same_sheet(self):
        """Two teachers, the same class, two phones."""
        for _ in range(2):
            save_sheet(template=self.template, academic_class=self.academic_class,
                       on_date=self.day, actor=self.user,
                       rows=self.rows(**{str(self.salah.pk): True}))

        self.assertEqual(StudentReport.objects.count(), 1)
        self.assertEqual(ReportAnswer.objects.count(), 1)

    def test_a_correction_overwrites_the_cell(self):
        save_sheet(template=self.template, academic_class=self.academic_class,
                   on_date=self.day, actor=self.user,
                   rows=self.rows(**{str(self.salah.pk): True}))
        save_sheet(template=self.template, academic_class=self.academic_class,
                   on_date=self.day, actor=self.user,
                   rows=self.rows(**{str(self.salah.pk): False}))

        self.assertIs(ReportAnswer.objects.get().value, False)

    def test_a_choice_outside_the_options_becomes_unanswered(self):
        """Not an error: one stray cell must not fail forty students' save."""
        save_sheet(template=self.template, academic_class=self.academic_class,
                   on_date=self.day, actor=self.user,
                   rows=self.rows(**{str(self.quran.pk): 'excellent'}))

        self.assertIsNone(ReportAnswer.objects.get().value)

    def test_a_number_that_is_not_a_number_becomes_unanswered(self):
        save_sheet(template=self.template, academic_class=self.academic_class,
                   on_date=self.day, actor=self.user,
                   rows=self.rows(**{str(self.paras.pk): 'twelve'}))

        self.assertIsNone(ReportAnswer.objects.get().value)

    def test_a_student_who_is_not_in_this_class_is_skipped(self):
        """The register decides who is on the sheet, not the payload."""
        other = Student.objects.create(
            branch=self.branch, stream=self.stream, student_id=allocate_student_id(),
            name='Not Here', admitted_on=date(2026, 1, 5))
        stray = Enrolment.objects.filter(student=other).first()

        result = save_sheet(
            template=self.template, academic_class=self.academic_class,
            on_date=self.day, actor=self.user,
            rows=[{'enrolment': (stray.pk if stray else 999999), 'answers': {}}])

        self.assertEqual(result['saved'], 0)
        self.assertEqual(result['skipped'][0]['reason'], 'not_enrolled')

    def test_the_period_follows_the_templates_frequency(self):
        self.template.frequency = ReportFrequency.MONTHLY
        self.template.save(update_fields=['frequency'])

        result = save_sheet(template=self.template, academic_class=self.academic_class,
                            on_date=self.day, actor=self.user,
                            rows=self.rows(**{str(self.salah.pk): True}))

        self.assertEqual(result['period'], '2026-09')
        self.assertEqual(StudentReport.objects.get().period, '2026-09')


class PeriodTests(TestCase):
    def test_each_frequency_names_its_own_period(self):
        day = date(2026, 9, 23)

        self.assertEqual(period_for(ReportFrequency.DAILY, day), '2026-09-23')
        self.assertEqual(period_for(ReportFrequency.WEEKLY, day), '2026-W39')
        self.assertEqual(period_for(ReportFrequency.MONTHLY, day), '2026-09')
        self.assertEqual(period_for(ReportFrequency.TERM, day), '2026-T3')


class ApiTests(ConductFixture, TestCase):
    def setUp(self):
        self.build()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_the_sheet_opens_on_the_right_template_without_being_asked(self):
        response = self.client.get('/api/conduct/sheet/',
                                   {'class': self.academic_class.pk,
                                    'date': '2026-09-23'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['template'], self.template.pk)
        self.assertEqual(len(response.data['students']), 3)

    def test_a_class_specific_template_beats_the_institutions(self):
        specific = ReportTemplate.objects.create(
            branch=self.branch, name='Hifz daily', section='conduct',
            academic_class=self.academic_class)

        response = self.client.get('/api/conduct/sheet/',
                                   {'class': self.academic_class.pk})

        self.assertEqual(response.data['template'], specific.pk)

    def test_filling_the_sheet_through_the_api(self):
        response = self.client.post('/api/conduct/sheet/', {
            'class': self.academic_class.pk,
            'date': '2026-09-23',
            'rows': [{'enrolment': self.enrolments[0].pk,
                      'answers': {str(self.salah.pk): True},
                      'remarks': 'আজ দেরিতে এসেছে'}],
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['saved'], 1)
        report = StudentReport.objects.get()
        self.assertEqual(report.remarks, 'আজ দেরিতে এসেছে')
        self.assertIsNotNone(report.filled_at)

    def test_another_institutions_class_is_404(self):
        from branches.models import InstitutionType
        from branches.services import create_branch
        from academics.models import AcademicClass
        from branches.models import Session

        other = create_branch(name='Chittagong', code='CTG',
                              institution_type=InstitutionType.MADRASAH)
        other_session = Session.objects.create(
            branch=other, name='2026', starts_on=date(2026, 1, 1),
            ends_on=date(2026, 12, 31))
        their_class = AcademicClass.objects.create(
            branch=other, session=other_session, stream=other.stream_set.first(),
            name='Class 5', year=2026)

        response = self.client.get('/api/conduct/sheet/', {'class': their_class.pk})

        self.assertEqual(response.status_code, 404)

    def test_a_teacher_may_not_fill_a_class_that_is_not_theirs(self):
        """docs/08 D6, the same gate the register and the marks grid use."""
        from django.contrib.auth import get_user_model
        from staff.services import create_teacher

        User = get_user_model()
        teacher_user = User.objects.create_user(
            phone='01711000055', password='pass-phrase-1234', name='Teacher',
            branch=self.branch, user_type='teacher',
            permissions=['conduct.view', 'conduct.take', 'academics.view'])
        create_teacher(branch=self.branch, name='Unassigned', user=teacher_user)

        client = APIClient()
        client.force_authenticate(teacher_user)
        response = client.get('/api/conduct/sheet/', {'class': self.academic_class.pk})

        self.assertEqual(response.status_code, 404)

    def test_reading_costs_view_and_filling_costs_take(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        reader = User.objects.create_user(
            phone='01711000066', password='pass-phrase-1234', name='Reader',
            branch=self.branch, user_type='accountant',
            permissions=['conduct.view'])

        client = APIClient()
        client.force_authenticate(reader)
        self.assertEqual(
            client.get('/api/conduct/sheet/',
                       {'class': self.academic_class.pk}).status_code, 200)
        self.assertEqual(
            client.post('/api/conduct/sheet/',
                        {'class': self.academic_class.pk,
                         'rows': [{'enrolment': self.enrolments[0].pk, 'answers': {}}]},
                        format='json').status_code, 403)

    def test_a_students_history_reads_back(self):
        self.client.post('/api/conduct/sheet/', {
            'class': self.academic_class.pk, 'date': '2026-09-23',
            'rows': [{'enrolment': self.enrolments[0].pk,
                      'answers': {str(self.salah.pk): True}}],
        }, format='json')

        response = self.client.get(
            f'/api/conduct/student/{self.enrolments[0].student_id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['reports']), 1)
        self.assertEqual(response.data['reports'][0]['period'], '2026-09-23')
