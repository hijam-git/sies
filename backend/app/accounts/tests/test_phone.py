"""Phone normalisation — CLAUDE.md §8 rule 4 names this as required.

The rule that matters is not "the function returns a string"; it is that all four
forms a human might type resolve to **one account**. A test that only checked the
function would still pass with a model that stored what it was given.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from accounts.phone import is_valid_bd_phone, normalize_bd_phone

from .factories import make_branch, make_user

CANONICAL = '01712345678'
EQUIVALENT_FORMS = [
    '+8801712345678',
    '8801712345678',
    '01712345678',
    '01712-345678',
    ' 017 1234 5678 ',
    '+88 01712-345678',
    # Written internationally, with the leading zero dropped.
    '1712345678',
]


class NormaliseTests(TestCase):
    def test_every_written_form_gives_the_same_number(self):
        for raw in EQUIVALENT_FORMS:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_bd_phone(raw), CANONICAL)

    def test_non_mobiles_normalise_to_empty_not_to_themselves(self):
        # Empty is falsy and cannot be mistaken for a number; returning the input
        # would let a caller that forgot to check store a landline as a login.
        for raw in ['', None, '0171234567', '017123456789', '021234567',
                    '01212345678', 'not a phone', '+9718001234567']:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_bd_phone(raw), '')
                self.assertFalse(is_valid_bd_phone(raw))


class OneAccountTests(TestCase):
    """The point of the whole exercise."""

    def setUp(self):
        self.branch = make_branch()

    def test_all_four_forms_reach_one_account(self):
        user = make_user(branch=self.branch, phone='+8801712345678')
        self.assertEqual(user.phone, CANONICAL)

        for raw in EQUIVALENT_FORMS:
            with self.subTest(raw=raw):
                self.assertEqual(User.objects.get_by_natural_key(raw).pk, user.pk)

    def test_a_second_account_in_another_form_is_refused(self):
        make_user(branch=self.branch, phone='01712345678')
        # Not a "you already have that" message from the app — the canonical
        # value is identical, so the unique index is what refuses it.
        with self.assertRaises(Exception):
            make_user(branch=self.branch, phone='+8801712345678')

    def test_save_normalises_whatever_path_wrote_it(self):
        user = make_user(branch=self.branch)
        user.phone = '+88 01799-887766'
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.phone, '01799887766')

    def test_save_refuses_a_number_that_cannot_be_normalised(self):
        user = make_user(branch=self.branch)
        user.phone = '01212345678'
        with self.assertRaises(ValidationError):
            user.save()
