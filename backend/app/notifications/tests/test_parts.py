"""What one message costs — the arithmetic a bill is built on.

A Bengali SMS is Unicode: **70 characters to a part, 67 once it is
concatenated**, not 160. The implementation this module was ported from divided
by 160 unconditionally, which under-charges a Bengali message by more than
half. These tests are the reason that cannot come back.
"""

from django.test import SimpleTestCase

from notifications.parts import is_gsm7, sms_cost, sms_length, sms_parts

BN = 'ফলাফল প্রকাশিত হয়েছে'          # 20 characters of Bangla
EN = 'Result published'


class EncodingTests(SimpleTestCase):
    def test_plain_english_is_gsm7(self):
        self.assertTrue(is_gsm7(EN))

    def test_one_bengali_character_moves_the_whole_message_to_unicode(self):
        self.assertFalse(is_gsm7(f'{EN} ফ'))

    def test_a_gsm7_extended_character_counts_twice(self):
        # '{' is sent as an escape plus a character — two of the 160.
        self.assertEqual(sms_length('{'), 2)
        self.assertEqual(sms_length('a'), 1)


class PartTests(SimpleTestCase):
    def test_english_fits_160_in_one_part(self):
        self.assertEqual(sms_parts('a' * 160), 1)
        self.assertEqual(sms_parts('a' * 161), 2)

    def test_english_concatenates_at_153(self):
        self.assertEqual(sms_parts('a' * 306), 2)
        self.assertEqual(sms_parts('a' * 307), 3)

    def test_bengali_fits_only_70_in_one_part(self):
        self.assertEqual(sms_parts('ক' * 70), 1)
        self.assertEqual(sms_parts('ক' * 71), 2)

    def test_bengali_concatenates_at_67(self):
        self.assertEqual(sms_parts('ক' * 134), 2)
        self.assertEqual(sms_parts('ক' * 135), 3)

    def test_the_default_result_message_is_one_sms(self):
        """The wording ships at one part per student, and that is the point of
        it: two would double every institution's results-day bill."""
        from notifications.services import DEFAULT_BODIES, render_body
        from notifications.models import NotificationEvent

        # A long Bengali name sitting a long Bengali exam — the case that
        # decides it, not a short one that would pass either way.
        body = render_body(DEFAULT_BODIES[(NotificationEvent.RESULT_PUBLISHED, 'bn')], {
            'student': 'মোহাম্মদ আব্দুল্লাহ', 'roll': 12,
            'exam': 'অর্ধবার্ষিক পরীক্ষা', 'grade': 'A+',
            'result': 'উত্তীর্ণ', 'institution': 'ঢাকা মাদ্রাসা',
        })

        self.assertEqual(sms_parts(body), 1, f'{len(body)} chars: {body}')

    def test_an_empty_body_is_one_part_not_zero(self):
        self.assertEqual(sms_parts(''), 1)


class CostTests(SimpleTestCase):
    def test_the_compose_screen_gets_what_it_needs(self):
        cost = sms_cost('ক' * 80)
        self.assertEqual(cost, {'characters': 80, 'encoding': 'unicode',
                                'per_part': 67, 'parts': 2})
