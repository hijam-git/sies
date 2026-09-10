"""What a new institution gets on day one.

Decision 1 of the "smart" list (docs/00 §2) is that **nobody types these in**.
Creating a branch creates its streams, its eleven fee categories and its income
and expense heads, in one transaction, chosen by `institution_type` (docs/08 D1).

The tables live here, as plain module-level constants, for three reasons:

1. They are *specified in docs/03* (§2, §7, §8) and belong with the institution,
   which is this app. `fees` and `finance` do not exist until Phase 5, and the
   data should not wait in someone's head until then.
2. Data, not code. D1 consequence 3 — "nothing may be hard-coded to a madrasah;
   every fee category name is data" — is only true if the names sit in a table
   an editor can read without following control flow.
3. `seed_branch()` stays a loop over these, so adding a category in Phase 5 is a
   row here rather than a branch in a function.

**`FEE_CATEGORY_SEEDS`, `INCOME_CATEGORY_SEEDS` and `EXPENSE_CATEGORY_SEEDS` are
not consumed yet.** `seeding.seed_branch()` seeds streams only, and says at the
one place where these plug in what has to happen when `fees` and `finance` land.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Streams — docs/00 §1, docs/03 §2, docs/08 D2a
#
# `code` is canonical and the same everywhere on the platform; `name_bn` is the
# institution's *own* label and is exactly what it may edit afterwards without a
# migration. A madrasah that writes হাফজ changes one row and keeps `hifz`.
# ─────────────────────────────────────────────────────────────────────────────

HIFZ = {'code': 'hifz', 'name': 'Hifz', 'name_bn': 'হিফজ', 'order': 10}
QAUMI = {'code': 'qaumi', 'name': 'Qaumi', 'name_bn': 'কওমি', 'order': 20}
GENERAL = {'code': 'general', 'name': 'General', 'name_bn': 'সাধারণ', 'order': 30}
SCIENCE = {'code': 'science', 'name': 'Science', 'name_bn': 'বিজ্ঞান', 'order': 40}
COMMERCE = {'code': 'commerce', 'name': 'Commerce', 'name_bn': 'ব্যবসায় শিক্ষা', 'order': 50}
ARTS = {'code': 'arts', 'name': 'Arts', 'name_bn': 'মানবিক', 'order': 60}

# Keyed by Branch.institution_type. A type missing from this map seeds nothing
# rather than raising: an institution with no streams is usable — its admin adds
# its own — whereas a branch that could not be created at all is not.
STREAM_SEEDS = {
    'madrasah': [HIFZ, QAUMI, GENERAL],
    'school': [GENERAL],
    'college': [SCIENCE, COMMERCE, ARTS],
    'combined': [HIFZ, QAUMI, GENERAL, SCIENCE, COMMERCE, ARTS],
}


# ─────────────────────────────────────────────────────────────────────────────
# Fee categories — docs/03 §7, the brief's eleven with their notes
#
# `note` is the brief's "proper note": the sentence the accountant reads in the
# UI when choosing a head, which is what stops Book Fee and Other Fee being used
# interchangeably. `is_system` rows may be deactivated but never deleted — a
# category a fee row points at is `PROTECT`ed anyway, and pretending otherwise
# would mean an accountant could orphan last year's invoices.
#
# Consumed by fees.FeeCategory in Phase 5. `recurrence` values match the
# `one_time / monthly / session / exam / custom` choices docs/03 §7 lists.
# ─────────────────────────────────────────────────────────────────────────────

FEE_CATEGORY_SEEDS = [
    {
        'code': 'ADM',
        'name': 'Admission Fee',
        'name_bn': 'ভর্তি ফি',
        'recurrence': 'one_time',
        'note': 'Charged once when a student is first admitted. Non-refundable.',
        'note_bn': 'শিক্ষার্থী প্রথম ভর্তি হওয়ার সময় একবার নেওয়া হয়। অফেরতযোগ্য।',
        'is_refundable': False,
        'is_mandatory': True,
        'is_system': True,
        'display_order': 10,
    },
    {
        'code': 'SES',
        'name': 'Session Fee',
        'name_bn': 'সেশন ফি',
        'recurrence': 'session',
        'note': 'Charged once per academic session at enrolment or re-admission.',
        'note_bn': 'প্রতি শিক্ষাবর্ষে ভর্তি বা পুনঃভর্তির সময় একবার নেওয়া হয়।',
        'is_refundable': False,
        'is_mandatory': True,
        'is_system': True,
        'display_order': 20,
    },
    {
        'code': 'MON',
        'name': 'Monthly Fee',
        'name_bn': 'মাসিক বেতন',
        'recurrence': 'monthly',
        'note': 'The regular tuition fee, raised automatically on the 1st of each month.',
        'note_bn': 'নিয়মিত বেতন, প্রতি মাসের ১ তারিখে স্বয়ংক্রিয়ভাবে ধার্য হয়।',
        'is_refundable': False,
        'is_mandatory': True,
        'is_system': True,
        'display_order': 30,
    },
    {
        'code': 'EXM',
        'name': 'Examination Fee',
        'name_bn': 'পরীক্ষার ফি',
        'recurrence': 'exam',
        'note': 'Charged per examination; raised when the exam is scheduled.',
        'note_bn': 'প্রতি পরীক্ষার জন্য; পরীক্ষার সময়সূচি নির্ধারিত হলে ধার্য হয়।',
        'is_refundable': False,
        'is_mandatory': True,
        'is_system': True,
        'display_order': 40,
    },
    {
        'code': 'BOK',
        'name': 'Book Fee',
        'name_bn': 'বই ফি',
        'recurrence': 'custom',
        'note': 'Textbooks and materials issued by the institution.',
        'note_bn': 'প্রতিষ্ঠান থেকে সরবরাহ করা পাঠ্যবই ও শিক্ষা উপকরণ।',
        'is_refundable': False,
        'is_mandatory': False,
        'is_system': True,
        'display_order': 50,
    },
    {
        'code': 'UNI',
        'name': 'Uniform Fee',
        'name_bn': 'ইউনিফর্ম ফি',
        'recurrence': 'custom',
        'note': 'Uniform issued or replaced.',
        'note_bn': 'ইউনিফর্ম সরবরাহ বা পরিবর্তন।',
        'is_refundable': False,
        'is_mandatory': False,
        'is_system': True,
        'display_order': 60,
    },
    {
        'code': 'TRN',
        'name': 'Transport Fee',
        'name_bn': 'পরিবহন ফি',
        'recurrence': 'monthly',
        'note': 'Charged only to students marked as using transport.',
        'note_bn': 'কেবল পরিবহন ব্যবহারকারী শিক্ষার্থীদের জন্য প্রযোজ্য।',
        'is_refundable': False,
        'is_mandatory': False,
        'is_system': True,
        'display_order': 70,
    },
    {
        'code': 'HOS',
        'name': 'Hostel Fee',
        'name_bn': 'হোস্টেল ফি',
        'recurrence': 'monthly',
        'note': 'Charged only to residential students; covers seat and utilities.',
        'note_bn': 'কেবল আবাসিক শিক্ষার্থীদের জন্য; সিট ও ইউটিলিটি খরচ অন্তর্ভুক্ত।',
        'is_refundable': False,
        'is_mandatory': False,
        'is_system': True,
        'display_order': 80,
    },
    {
        'code': 'FOD',
        'name': 'Food Fee',
        'name_bn': 'খাবার ফি',
        'recurrence': 'monthly',
        'note': 'Meals for residential students, where billed separately from hostel.',
        'note_bn': 'আবাসিক শিক্ষার্থীদের খাবার, হোস্টেল ফি থেকে আলাদাভাবে হিসাব হলে।',
        'is_refundable': False,
        'is_mandatory': False,
        'is_system': True,
        'display_order': 90,
    },
    {
        'code': 'ACT',
        'name': 'Activity Fee',
        'name_bn': 'কার্যক্রম ফি',
        'recurrence': 'session',
        'note': 'Sports, cultural programmes, milad, annual events.',
        'note_bn': 'খেলাধুলা, সাংস্কৃতিক অনুষ্ঠান, মিলাদ ও বার্ষিক আয়োজন।',
        'is_refundable': False,
        'is_mandatory': False,
        'is_system': True,
        'display_order': 100,
    },
    {
        'code': 'OTH',
        'name': 'Other Fee',
        'name_bn': 'অন্যান্য ফি',
        'recurrence': 'custom',
        'note': 'Anything not covered above; always give a reason in the remarks.',
        'note_bn': 'উপরের কোনোটিতে না পড়লে; মন্তব্যে অবশ্যই কারণ লিখুন।',
        'is_refundable': False,
        'is_mandatory': False,
        'is_system': True,
        'display_order': 110,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Income and expense heads — docs/03 §8
#
# `fee_category` names the FeeCategory *code* whose collections post here. That
# link is what makes item 4 of the "smart" list work — a recorded payment writes
# its Income row by itself, and the two can never disagree because nobody typed
# the second one. Hostel, Transport and Other Income exist for exactly that
# reason: the fee categories above generate them, and an unmapped receipt would
# otherwise land in a null head.
# ─────────────────────────────────────────────────────────────────────────────

INCOME_CATEGORY_SEEDS = [
    {'code': 'INC-ADM', 'name': 'Admission Fee', 'name_bn': 'ভর্তি ফি',
     'fee_category': 'ADM', 'display_order': 10,
     'note': 'Admission fees collected from students.',
     'note_bn': 'শিক্ষার্থীদের কাছ থেকে আদায়কৃত ভর্তি ফি।'},
    {'code': 'INC-SES', 'name': 'Session Fee', 'name_bn': 'সেশন ফি',
     'fee_category': 'SES', 'display_order': 20,
     'note': 'Session fees collected at enrolment or re-admission.',
     'note_bn': 'ভর্তি বা পুনঃভর্তির সময় আদায়কৃত সেশন ফি।'},
    {'code': 'INC-MON', 'name': 'Monthly Fee', 'name_bn': 'মাসিক বেতন',
     'fee_category': 'MON', 'display_order': 30,
     'note': 'Regular monthly tuition collected from students.',
     'note_bn': 'শিক্ষার্থীদের নিয়মিত মাসিক বেতন।'},
    {'code': 'INC-EXM', 'name': 'Examination Fee', 'name_bn': 'পরীক্ষার ফি',
     'fee_category': 'EXM', 'display_order': 40,
     'note': 'Examination fees collected per exam.',
     'note_bn': 'প্রতি পরীক্ষায় আদায়কৃত পরীক্ষার ফি।'},
    {'code': 'INC-BOK', 'name': 'Book Sale', 'name_bn': 'বই বিক্রয়',
     'fee_category': 'BOK', 'display_order': 50,
     'note': 'Sale of textbooks and materials.',
     'note_bn': 'পাঠ্যবই ও শিক্ষা উপকরণ বিক্রয়।'},
    {'code': 'INC-HOS', 'name': 'Hostel Income', 'name_bn': 'হোস্টেল আয়',
     'fee_category': 'HOS', 'display_order': 60,
     'note': 'Hostel seat and utility charges collected.',
     'note_bn': 'আদায়কৃত হোস্টেল সিট ও ইউটিলিটি চার্জ।'},
    {'code': 'INC-TRN', 'name': 'Transport Income', 'name_bn': 'পরিবহন আয়',
     'fee_category': 'TRN', 'display_order': 70,
     'note': 'Transport charges collected from students.',
     'note_bn': 'শিক্ষার্থীদের কাছ থেকে আদায়কৃত পরিবহন চার্জ।'},
    {'code': 'INC-DON', 'name': 'Donation', 'name_bn': 'অনুদান',
     'fee_category': None, 'display_order': 80,
     'note': 'Donations and sadaqah received by the institution.',
     'note_bn': 'প্রতিষ্ঠানে প্রাপ্ত অনুদান ও সদকা।'},
    {'code': 'INC-OTH', 'name': 'Other Income', 'name_bn': 'অন্যান্য আয়',
     'fee_category': 'OTH', 'display_order': 90,
     'note': 'Anything not covered above; give a reason in the description.',
     'note_bn': 'উপরের কোনোটিতে না পড়লে; বিবরণে কারণ লিখুন।'},
]

EXPENSE_CATEGORY_SEEDS = [
    {'code': 'EXP-TSAL', 'name': 'Teacher Salary', 'name_bn': 'শিক্ষক বেতন',
     'display_order': 10,
     'note': 'Salary paid to teaching staff.',
     'note_bn': 'শিক্ষকদের বেতন।'},
    # Separated from Teacher Salary on purpose: payroll reporting splits the way
    # institutions actually budget, and merging them hides the larger of the two.
    {'code': 'EXP-SSAL', 'name': 'Staff Salary', 'name_bn': 'কর্মচারী বেতন',
     'display_order': 20,
     'note': 'Salary paid to non-teaching staff.',
     'note_bn': 'অশিক্ষক কর্মচারীদের বেতন।'},
    {'code': 'EXP-ELEC', 'name': 'Electricity', 'name_bn': 'বিদ্যুৎ',
     'display_order': 30, 'note': 'Electricity bills.', 'note_bn': 'বিদ্যুৎ বিল।'},
    {'code': 'EXP-NET', 'name': 'Internet', 'name_bn': 'ইন্টারনেট',
     'display_order': 40, 'note': 'Internet and telephone bills.',
     'note_bn': 'ইন্টারনেট ও টেলিফোন বিল।'},
    {'code': 'EXP-RENT', 'name': 'Rent', 'name_bn': 'ভাড়া',
     'display_order': 50, 'note': 'Building or premises rent.',
     'note_bn': 'ভবন বা প্রাঙ্গণের ভাড়া।'},
    {'code': 'EXP-BOOK', 'name': 'Books', 'name_bn': 'বই',
     'display_order': 60, 'note': 'Books purchased for the institution or library.',
     'note_bn': 'প্রতিষ্ঠান বা পাঠাগারের জন্য ক্রয়কৃত বই।'},
    {'code': 'EXP-STAT', 'name': 'Stationery', 'name_bn': 'স্টেশনারি',
     'display_order': 70, 'note': 'Office and classroom stationery.',
     'note_bn': 'অফিস ও শ্রেণিকক্ষের স্টেশনারি।'},
    {'code': 'EXP-MAIN', 'name': 'Maintenance', 'name_bn': 'রক্ষণাবেক্ষণ',
     'display_order': 80, 'note': 'Repairs and upkeep of buildings and equipment.',
     'note_bn': 'ভবন ও সরঞ্জামের মেরামত ও রক্ষণাবেক্ষণ।'},
    {'code': 'EXP-FOOD', 'name': 'Food', 'name_bn': 'খাবার',
     'display_order': 90, 'note': 'Kitchen and meal costs.',
     'note_bn': 'রান্নাঘর ও খাবারের খরচ।'},
    {'code': 'EXP-TRN', 'name': 'Transport', 'name_bn': 'পরিবহন',
     'display_order': 100, 'note': 'Vehicle fuel, hire and upkeep.',
     'note_bn': 'যানবাহনের জ্বালানি, ভাড়া ও রক্ষণাবেক্ষণ।'},
    {'code': 'EXP-EQP', 'name': 'Equipment', 'name_bn': 'সরঞ্জাম',
     'display_order': 110, 'note': 'Furniture, computers and other equipment.',
     'note_bn': 'আসবাব, কম্পিউটার ও অন্যান্য সরঞ্জাম।'},
    {'code': 'EXP-MKT', 'name': 'Marketing', 'name_bn': 'প্রচার',
     'display_order': 120, 'note': 'Admission campaigns, posters and publicity.',
     'note_bn': 'ভর্তি প্রচারণা, পোস্টার ও প্রচার খরচ।'},
    {'code': 'EXP-OTH', 'name': 'Other Expense', 'name_bn': 'অন্যান্য খরচ',
     'display_order': 130,
     'note': 'Anything not covered above; give a reason in the description.',
     'note_bn': 'উপরের কোনোটিতে না পড়লে; বিবরণে কারণ লিখুন।'},
]
