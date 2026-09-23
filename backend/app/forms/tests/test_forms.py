"""The guarantees docs/07 exists to make (CLAUDE.md §4a).

Each of these, if it broke, would be discovered by somebody holding a printed
form — which is why they are tested here rather than trusted to a code review.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase

from forms.models import AdmissionAnswer, FormTemplate, PrintedForm, Question
from forms.services import print_form, save_answers
from forms.renderer import render_form

from . import factories as f


class TemplateValidationTests(TestCase):
    """An unknown placeholder is a validation error **when the template is
    saved**, never a silent blank at print time (§4).

    The silent-blank failure is the one worth preventing: a typo renders as an
    empty rule, which looks exactly like a deliberate blank, so nobody notices
    until two hundred forms have been printed with the applicant's name missing.
    """

    def setUp(self):
        self.branch = f.make_branch()

    def _template(self, blocks, name='Custom'):
        return FormTemplate(branch=self.branch, name=name, form_type='admission',
                            blocks=blocks)

    def test_an_unknown_placeholder_is_rejected_at_save(self):
        template = self._template([
            {'type': 'prose', 'text': 'আমি {{student.namebn}} ইবনে'},
        ])
        with self.assertRaises(DjangoValidationError) as caught:
            template.save()
        self.assertIn('student.namebn', str(caught.exception))
        self.assertFalse(FormTemplate.objects.filter(name='Custom').exists())

    def test_a_known_placeholder_saves(self):
        self._template([{'type': 'prose', 'text': 'আমি {{student.name_bn}}'}]).save()
        self.assertTrue(FormTemplate.objects.filter(name='Custom').exists())

    def test_an_unknown_placeholder_in_a_bullet_is_rejected(self):
        """Every text-bearing key is validated, not only prose blocks."""
        template = self._template([
            {'type': 'bullet_list', 'items': ['আমার সন্তান {{student.nam}}']},
        ])
        with self.assertRaises(DjangoValidationError):
            template.save()

    def test_the_seeded_template_validates(self):
        """The reference form is the strongest single case for the validator."""
        template = f.admission_template(self.branch)
        template.save()  # re-validates; raises if any seeded block is malformed
        self.assertTrue(template.blocks)


class MalformedBlockTests(TestCase):
    """A malformed block cannot reach the renderer (§6.1).

    The database cannot check a JSON document's shape, so `save()` does — and it
    refuses in front of the administrator who typed it, rather than printing a
    page with a section silently missing.
    """

    def setUp(self):
        self.branch = f.make_branch()

    def _save(self, blocks):
        FormTemplate(branch=self.branch, name='Custom', form_type='admission',
                     blocks=blocks).save()

    def test_an_unknown_block_type_is_rejected(self):
        with self.assertRaises(DjangoValidationError):
            self._save([{'type': 'marquee', 'text': 'hello'}])

    def test_a_block_missing_a_required_key_is_rejected(self):
        with self.assertRaises(DjangoValidationError):
            self._save([{'type': 'prose'}])

    def test_a_misspelled_key_is_rejected(self):
        """`{"type": "prose", "txt": …}` would otherwise render an empty paragraph."""
        with self.assertRaises(DjangoValidationError):
            self._save([{'type': 'prose', 'txt': 'hello'}])

    def test_a_wrongly_typed_key_is_rejected(self):
        with self.assertRaises(DjangoValidationError):
            self._save([{'type': 'bullet_list', 'items': 'not a list'}])

    def test_blocks_must_be_a_list(self):
        with self.assertRaises(DjangoValidationError):
            self._save({'type': 'prose', 'text': 'hello'})


class MapsToTests(TestCase):
    """§5.2 — a question either maps to a field or stores an answer, never both.

    Without this, "previous institution" ends up in `Student` *and* in
    `AdmissionAnswer`, the two disagree within a month, and no report built on
    either can be trusted.
    """

    def setUp(self):
        self.world = f.small_world()
        self.student = f.make_student(self.world['branch'])
        self.admission = self.world['admission']
        self.admission.student = self.student
        self.admission.status = 'admitted'
        self.admission.save(update_fields=['student', 'status'])

    def test_a_mapped_question_writes_the_student_field_and_stores_no_answer(self):
        question = Question.objects.get(maps_to='previous_institution')

        save_answers(admission=self.admission,
                     answers={question.pk: 'Dasherbari Madrasah'},
                     actor=self.world['user'])

        self.student.refresh_from_db()
        self.assertEqual(self.student.previous_institution, 'Dasherbari Madrasah')
        self.assertEqual(AdmissionAnswer.objects.count(), 0)

    def test_an_unmapped_question_stores_an_answer_and_touches_no_field(self):
        question = f.make_question(self.world['branch'])

        save_answers(admission=self.admission, answers={question.pk: 'না'},
                     actor=self.world['user'])

        answer = AdmissionAnswer.objects.get()
        self.assertEqual(answer.value, 'না')
        self.assertEqual(answer.question_id, question.pk)

    def test_answering_twice_updates_the_one_row(self):
        question = f.make_question(self.world['branch'])
        save_answers(admission=self.admission, answers={question.pk: 'ক'},
                     actor=self.world['user'])
        save_answers(admission=self.admission, answers={question.pk: 'খ'},
                     actor=self.world['user'])
        self.assertEqual(AdmissionAnswer.objects.count(), 1)
        self.assertEqual(AdmissionAnswer.objects.get().value, 'খ')

    def test_before_admission_the_field_is_written_on_the_application(self):
        """Most applications never become a Student; the application is the record."""
        admission = f.make_admission(
            self.world['branch'], self.world['session'], self.world['class'],
            application_no='APP-0002',
        )
        question = Question.objects.get(maps_to='previous_class')

        save_answers(admission=admission, answers={question.pk: 'হিফজ'},
                     actor=self.world['user'])

        admission.refresh_from_db()
        self.assertEqual(admission.previous_class, 'হিফজ')
        self.assertEqual(AdmissionAnswer.objects.count(), 0)


class ReusableQuestionTests(TestCase):
    """A question with no template belongs to every form of the institution.

    `form_questions` asked for `template__in=[None, template.pk]`, and SQL's
    `IN (NULL, 4)` never matches a NULL row — so every reusable question was
    dropped from every form. Saved, listed on the question screen, printed
    nowhere, and no error anywhere to say so. It is the kind the screen itself
    recommends making ("leave blank and every form of this institution may ask
    it"), which is why nobody could see their questions on the admission form.
    """

    def setUp(self):
        self.world = f.small_world()

    def make_question(self, *, template, text_bn, section='admission'):
        from forms.models import Question, QuestionType

        return Question.objects.create(
            branch=self.world['branch'], template=template, section=section,
            type=QuestionType.SHORT_TEXT, text='Q', text_bn=text_bn, order=50,
        )

    def test_a_question_with_no_template_prints_on_the_form(self):
        from forms.services import form_questions

        reusable = self.make_question(template=None, text_bn='পূর্বের মাদ্রাসা')

        picked = form_questions(self.world['branch'], self.world['template'])

        self.assertIn(reusable, picked)

    def test_it_reaches_the_rendered_page_and_not_only_the_queryset(self):
        from forms.placeholders import build_context
        from forms.services import form_questions

        self.make_question(template=None, text_bn='পূর্বের মাদ্রাসা')
        template = self.world['template']

        html = render_form(
            template=template,
            context=build_context(branch=self.world['branch'],
                                  admission=self.world['admission']),
            questions=form_questions(self.world['branch'], template),
            mode='filled',
        )

        self.assertIn('পূর্বের মাদ্রাসা', html)

    def test_a_question_bound_to_another_template_stays_off_this_one(self):
        """The other half of the rule — the binding still means something."""
        from forms.models import FormTemplate
        from forms.services import form_questions

        other = FormTemplate.objects.create(
            branch=self.world['branch'], name='Transfer form', form_type='admission',
            blocks=[], paper='a4',
        )
        theirs = self.make_question(template=other, text_bn='শুধু ছাড়পত্রের প্রশ্ন')

        picked = form_questions(self.world['branch'], self.world['template'])

        self.assertNotIn(theirs, picked)


class BlankAndFilledTests(TestCase):
    """One template, two outputs (§7) — so the two can never drift."""

    def setUp(self):
        self.world = f.small_world()

    def test_blank_renders_rules_where_filled_renders_values(self):
        from forms.placeholders import build_context

        template = self.world['template']
        context = build_context(branch=self.world['branch'],
                                admission=self.world['admission'])

        filled = render_form(template=template, context=context, mode='filled')
        blank = render_form(template=template, context=context, mode='blank')

        # The applicant's name is on the filled form and nowhere on the blank.
        self.assertIn('রহিম উদ্দিন', filled)
        self.assertNotIn('রহিম উদ্দিন', blank)

        # Both are the same document: the fixed template text prints on both,
        # and the blank has strictly more empty rules than the filled one.
        self.assertIn('বিনীত নিবেদন', filled)
        self.assertIn('বিনীত নিবেদন', blank)
        self.assertGreater(blank.count('class="rule"'), filled.count('class="rule"'))
        self.assertIn('class="rule filled"', filled)

    def test_a_filled_value_prints_without_a_line_under_it(self):
        """The rule is a line to WRITE on.

        It was drawn under filled values too, so every typed answer on a
        printed form came out underlined — which reads as emphasis, or as a
        correction, on a document a guardian signs and the office files. The
        blanks keep their rule; that is what they are for.
        """
        template = self.world['template']

        css = render_form(template=template, mode='filled')

        self.assertIn('.rule.filled { border-bottom: none;', css)
        # And the blanks still have theirs.
        self.assertIn('.rule { display: inline-block;', css)
        self.assertIn('border-bottom: 1px dotted #000', css)

    def test_both_modes_produce_a_printable_a4_document(self):
        template = self.world['template']
        for mode in ('blank', 'filled'):
            html = render_form(template=template, mode=mode)
            self.assertIn('@page { size: A4; margin: 12mm 14mm; }', html)
            self.assertIn('<!DOCTYPE html>', html)


class SnapshotTests(TestCase):
    """§6 — a reprint shows what was signed, not what the record says today."""

    def setUp(self):
        self.world = f.small_world()
        self.student = f.make_student(self.world['branch'], name_bn='রহিম উদ্দিন')
        self.admission = self.world['admission']
        self.admission.student = self.student
        self.admission.status = 'admitted'
        self.admission.save(update_fields=['student', 'status'])

    def test_a_reprint_still_shows_the_old_values(self):
        from forms.services import reprint

        html, printed = print_form(admission=self.admission,
                                   actor=self.world['user'])
        self.assertIn('রহিম উদ্দিন', html)

        # A name correction a year later — the commonest kind of edit there is.
        self.student.name_bn = 'রহিমুল ইসলাম'
        self.student.save(update_fields=['name_bn'])
        self.admission.applicant_name_bn = 'রহিমুল ইসলাম'
        self.admission.save(update_fields=['applicant_name_bn'])

        again = reprint(printed, actor=self.world['user'])
        self.assertIn('রহিম উদ্দিন', again)
        self.assertNotIn('রহিমুল ইসলাম', again)

        printed.refresh_from_db()
        self.assertEqual(printed.reprint_count, 1)

    def test_a_fresh_print_shows_the_new_values(self):
        """The snapshot freezes the printed copy, not the institution's records."""
        print_form(admission=self.admission, actor=self.world['user'])
        self.admission.applicant_name_bn = 'রহিমুল ইসলাম'
        self.admission.save(update_fields=['applicant_name_bn'])
        self.student.name_bn = 'রহিমুল ইসলাম'
        self.student.save(update_fields=['name_bn'])

        html, _printed = print_form(admission=self.admission, actor=self.world['user'])
        self.assertIn('রহিমুল ইসলাম', html)


class FormNumberTests(TestCase):
    """`form_no` is its own per-branch gapless sequence (§6, CLAUDE.md §4.4)."""

    def setUp(self):
        self.world = f.small_world()

    def test_form_numbers_are_gapless_and_sequential(self):
        numbers = [
            print_form(admission=self.world['admission'],
                       actor=self.world['user'])[1].form_no
            for _ in range(3)
        ]
        self.assertEqual(numbers, ['FRM-DHK-00001', 'FRM-DHK-00002', 'FRM-DHK-00003'])

    def test_each_institution_counts_its_own(self):
        """A shared counter would let Dhaka issuing 1 push Chittagong to 2."""
        other = f.small_world(code='CTG', phone='01722000001')
        _html, dhaka = print_form(admission=self.world['admission'],
                                  actor=self.world['user'])
        _html, ctg = print_form(admission=other['admission'], actor=other['user'])
        self.assertEqual(dhaka.form_no, 'FRM-DHK-00001')
        self.assertEqual(ctg.form_no, 'FRM-CTG-00001')

    def test_a_blank_burns_no_number(self):
        """A blank is one sheet off a stack of two hundred; numbering each one
        would make the series meaningless as a record of applications."""
        html, printed = print_form(admission=self.world['admission'],
                                   mode='blank', actor=self.world['user'])
        self.assertIsNone(printed)
        self.assertEqual(PrintedForm.objects.count(), 0)
        self.assertIn('বিনীত নিবেদন', html)


class SeedingTests(TestCase):
    """A new branch prints a usable form on day one (§10)."""

    def test_seeding_is_idempotent(self):
        from forms.seeding import seed_form_templates

        branch = f.make_branch()  # already seeded once
        again = seed_form_templates(branch)
        self.assertEqual(again, {'form_templates': 0, 'questions': 0})
        self.assertEqual(FormTemplate.objects.filter(branch=branch).count(), 1)
        self.assertEqual(Question.objects.filter(branch=branch).count(), 3)

    def test_a_school_gets_no_madrasah_form(self):
        """docs/08 D1 — nothing may be hard-coded to one institution type."""
        school = f.make_branch(code='SCH', name='City School',
                               institution_type='school')
        self.assertEqual(FormTemplate.objects.filter(branch=school).count(), 0)
