"""Grading: the two methods, the scale lookup, seeding, and freezing at publish.

The arithmetic tests use presets and hand-built papers, so each names one rule
of a Bangladeshi marksheet and nothing else can make it pass.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from exams.grading import (DIVISION, GPA, evaluate, preset_scale, reset_to_preset,
                           scale_for, seed_grade_scales)
from exams.models import GradeScale, Result
from exams.services import publish_exam, save_marks, student_result, tabulation

from . import factories as f

D = Decimal


def paper(name, obtained, *, full='100', pass_mark='33', absent=False, optional=False):
    return {'name': name, 'full': D(full), 'pass_mark': D(pass_mark),
            'obtained': D('0') if absent else D(obtained), 'is_absent': absent,
            'is_optional': optional}


class GpaMethodTests(TestCase):
    scale = preset_scale(GPA)

    def test_gpa_is_the_average_of_subject_points_not_of_the_total(self):
        graded, result = evaluate(self.scale, [paper('Bangla', '90'), paper('Math', '50')])
        self.assertEqual([g['grade'] for g in graded], ['A+', 'B'])
        self.assertEqual(result['gpa'], D('4.00'))
        self.assertEqual(result['grade'], 'A')
        self.assertTrue(result['is_passed'])

    def test_an_uneven_average_rounds_to_two_places(self):
        _, result = evaluate(self.scale, [paper('A', '90'), paper('B', '75'), paper('C', '65')])
        # (5 + 4 + 3.5) / 3 = 4.1666… → 4.17, graded A.
        self.assertEqual(result['gpa'], D('4.17'))
        self.assertEqual(result['grade'], 'A')

    def test_failing_any_compulsory_subject_fails_with_gpa_zero(self):
        _, result = evaluate(self.scale, [paper('Bangla', '95'), paper('Math', '20')])
        self.assertFalse(result['is_passed'])
        self.assertEqual(result['gpa'], D('0.00'))
        self.assertEqual(result['grade'], 'F')
        self.assertEqual(result['failed_subjects'], ['Math'])

    def test_absent_fails_the_subject(self):
        graded, result = evaluate(self.scale, [paper('Bangla', '80'), paper('Math', '0', absent=True)])
        self.assertFalse(graded[1]['is_passed'])
        self.assertFalse(result['is_passed'])

    def test_the_optional_subject_adds_only_points_above_two(self):
        _, result = evaluate(self.scale, [
            paper('Bangla', '60'), paper('Math', '60'),        # 3.5 + 3.5
            paper('Agriculture', '70', optional=True),         # 4 → +2
        ])
        # (7 + 2) / 2 = 4.50
        self.assertEqual(result['gpa'], D('4.50'))

    def test_gpa_never_exceeds_the_top_point(self):
        _, result = evaluate(self.scale, [
            paper('Bangla', '85'), paper('Math', '85'), paper('Agriculture', '85', optional=True),
        ])
        self.assertEqual(result['gpa'], D('5.00'))

    def test_failing_the_optional_subject_fails_nothing(self):
        _, result = evaluate(self.scale, [
            paper('Bangla', '70'), paper('Agriculture', '10', optional=True),
        ])
        self.assertTrue(result['is_passed'])
        self.assertEqual(result['gpa'], D('4.00'))

    def test_a_pass_below_the_lowest_band_takes_the_lowest_passing_grade(self):
        graded, result = evaluate(self.scale, [paper('Bangla', '30', pass_mark='25')])
        self.assertEqual(graded[0]['grade'], 'D')
        self.assertTrue(result['is_passed'])


class DivisionMethodTests(TestCase):
    scale = preset_scale(DIVISION)

    def test_one_grade_from_the_total_and_no_gpa(self):
        _, result = evaluate(self.scale, [paper('Nahw', '90'), paper('Fiqh', '80')])
        self.assertEqual(result['percentage'], D('85.00'))
        self.assertEqual(result['grade_bn'], 'মুমতাজ')
        self.assertIsNone(result['gpa'])

    def test_the_middle_bands(self):
        _, jayyid = evaluate(self.scale, [paper('Nahw', '55'), paper('Fiqh', '55')])
        self.assertEqual(jayyid['grade_bn'], 'জায়্যিদ')
        _, maqbul = evaluate(self.scale, [paper('Nahw', '40'), paper('Fiqh', '40')])
        self.assertEqual(maqbul['grade_bn'], 'মাকবুল')

    def test_a_failed_subject_is_rasib_whatever_the_total(self):
        _, result = evaluate(self.scale, [paper('Nahw', '99'), paper('Fiqh', '10')])
        self.assertFalse(result['is_passed'])
        self.assertEqual(result['grade_bn'], 'রাসিব')


class ScaleLookupAndSeedingTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        self.branch = self.world['branch']

    def test_a_new_institution_gets_a_scale_per_stream(self):
        methods = dict(GradeScale.objects.filter(branch=self.branch)
                       .values_list('stream__code', 'method'))
        self.assertEqual(methods, {'hifz': DIVISION, 'qaumi': DIVISION, 'general': GPA})
        self.assertEqual(seed_grade_scales(self.branch), 0, 're-seeding must create nothing')

    def test_the_exams_stream_scale_is_used(self):
        general = GradeScale.objects.get(branch=self.branch, stream__code='general')
        reset_to_preset(general, DIVISION)
        self.assertEqual(scale_for(self.world['exam']).method, DIVISION)

    def test_it_falls_back_to_the_institution_default_then_the_preset(self):
        GradeScale.objects.filter(branch=self.branch, stream__code='general').delete()
        default = GradeScale.objects.create(branch=self.branch, stream=None,
                                            name='Default', method=DIVISION)
        reset_to_preset(default, DIVISION)
        self.assertEqual(scale_for(self.world['exam']).method, DIVISION)

        default.delete()
        self.assertEqual(scale_for(self.world['exam']).method, GPA)


class PublishFreezesResultsTests(TestCase):
    """A published marksheet does not move when the scale is edited."""

    def setUp(self):
        self.world = f.small_world()
        w = self.world
        for subject in (w['arabic'], w['fiqh']):
            save_marks(exam=w['exam'], subject=subject, actor=w['principal'],
                       rows=[{'enrolment': w['enrolments'][0].pk, 'obtained': '85'}])
        self.student = w['students'][0]
        self.scale = GradeScale.objects.get(branch=w['branch'], stream__code='general')

    def _raise_the_a_plus_floor(self):
        band = self.scale.bands.get(grade='A+')
        band.min_percent = D('90')
        band.save()

    def test_an_open_exam_follows_the_scale(self):
        self.assertEqual(student_result(self.world['exam'], self.student)['grade'], 'A+')
        self._raise_the_a_plus_floor()
        self.assertEqual(student_result(self.world['exam'], self.student)['grade'], 'A')

    def test_a_published_result_is_frozen(self):
        exam = self.world['exam']
        publish_exam(exam, actor=self.world['principal'])
        self.assertEqual(Result.objects.filter(exam=exam).count(), 2)

        self._raise_the_a_plus_floor()

        self.assertEqual(student_result(exam, self.student)['grade'], 'A+')
        row = next(r for r in tabulation(exam, self.world['class'])['rows']
                   if r['student'] == self.student.pk)
        self.assertEqual(row['grade'], 'A+')
        self.assertEqual(row['rank_in_class'], 1)


@override_settings(ROOT_URLCONF='exams.tests.urls')
class GradeScaleApiTests(TestCase):
    def setUp(self):
        self.world = f.small_world()
        self.client = APIClient()
        self.client.force_authenticate(self.world['principal'])
        self.scale = GradeScale.objects.get(branch=self.world['branch'], stream__code='general')
        self.url = f'/api/grade-scales/{self.scale.pk}/'

    def _bands(self, *rows):
        return [{'min_percent': floor, 'grade': grade, 'grade_bn': '', 'point': point,
                 'is_fail': fail} for floor, grade, point, fail in rows]

    def test_the_institutions_scales_are_listed(self):
        response = self.client.get('/api/grade-scales/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 3)

    def test_bands_are_replaced_whole(self):
        response = self.client.patch(self.url, {'bands': self._bands(
            ('50', 'Pass', '1.00', False), ('0', 'Fail', '0.00', True),
        )}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([b['grade'] for b in response.json()['bands']], ['Pass', 'Fail'])
        self.assertEqual(self.scale.bands.count(), 2)

    def test_two_grades_on_one_floor_are_refused(self):
        response = self.client.patch(self.url, {'bands': self._bands(
            ('50', 'A', '4.00', False), ('50', 'B', '3.00', False),
        )}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_a_scale_with_no_pass_is_refused(self):
        response = self.client.patch(self.url, {'bands': self._bands(('0', 'F', '0.00', True))},
                                     format='json')
        self.assertEqual(response.status_code, 400)

    def test_reset_switches_the_method(self):
        response = self.client.post(f'{self.url}reset/', {'method': 'division'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['method'], 'division')
        self.assertIn('মুমতাজ', [b['grade_bn'] for b in response.json()['bands']])

    def test_editing_needs_settings_update(self):
        viewer = f.make_user(self.world['branch'], phone='01799200001',
                             permissions=['settings.view', 'exams.update'])
        client = APIClient()
        client.force_authenticate(viewer)
        self.assertEqual(client.get('/api/grade-scales/').status_code, 200)
        self.assertEqual(client.patch(self.url, {'is_active': False}, format='json').status_code, 403)

    def test_another_institutions_scale_is_404(self):
        other = f.small_world(code='CTG', phone='01711000099')
        client = APIClient()
        client.force_authenticate(other['principal'])
        self.assertEqual(client.get(self.url).status_code, 404)
