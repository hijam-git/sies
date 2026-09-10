"""The reference admission form, as data (docs/07 §10).

A new branch prints a usable, correct ভর্তি ফরম on day one and edits the pledge
wording only if it wants to — the same principle as the seeded fee categories:
the system arrives knowing how a Bangladeshi madrasah works, rather than asking
the admin to teach it.

It is a module-level constant, and that is the point of §2's design. Everything
below is *data*: block order, prose, pledges, office-panel labels. Changing the
printed form is editing rows here or, for one institution, editing its template
in the UI. Nothing about this form is in code, so the next branch does not need
a developer.

Keyed by `Branch.institution_type` (docs/08 D1 — nothing may be hard-coded to a
madrasah). Only `madrasah` is written out here because it is the form that was
scanned and specified; a school or college seeds no template until its own is
specified, which prints nothing rather than printing a madrasah's letter under a
school's name.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Page 1
# ─────────────────────────────────────────────────────────────────────────────

LETTERHEAD = {
    'type': 'letterhead',
    'show_logo': True,
    # Arabic first, exactly as the scanned form has it. It reads right to left
    # and is set in an Arabic face by the renderer.
    'lines_ar': ['{{branch.name_ar}}'],
    'lines': [
        '{{branch.name_bn}}',
        '{{branch.name}}',
        'স্থাপিত: {{branch.established_year}} ইং',
        '{{branch.address_bn}}',
    ],
}

META_ROW = {
    'type': 'meta_row',
    'fields': [
        {'label': 'ফরম নং', 'value': '{{form.form_no}}'},
        {'label': 'ভর্তি নং', 'value': '{{form.admission_no}}'},
        {'label': 'শিক্ষাবর্ষ', 'value': '{{form.session}}'},
        {'label': 'তারিখ', 'value': '{{form.date}}'},
    ],
}

TITLE = {'type': 'prose', 'text': 'ভর্তি ফরম', 'text_bn': 'ভর্তি ফরম', 'align': 'center'}

# The application letter. Its blanks are placeholders, so the same paragraph
# prints as ruled gaps on a blank form and as underlined values on a filled one
# (§4, §7) — one paragraph, never two versions that drift.
LETTER_HEAD_LINES = {
    'type': 'prose',
    'text': 'মাননীয় {{branch.head_title}} সাহেব\n{{branch.name_bn}}\n{{branch.address_bn}}',
    'text_bn': 'মাননীয় {{branch.head_title}} সাহেব\n{{branch.name_bn}}\n{{branch.address_bn}}',
}

SUBJECT_LINE = {
    'type': 'prose',
    'text': 'বিষয়: ভর্তির জন্য আবেদন।',
    'text_bn': 'বিষয়: ভর্তির জন্য আবেদন।',
}

LETTER_BODY = {
    'type': 'prose',
    'indent': True,
    'text': ('বিনীত নিবেদন এই যে, আমি {{student.name_bn}} ইবনে/বিনতে '
             '{{guardian.father_name_bn}}, গ্রাম {{address.village}}, ডাকঘর '
             '{{address.post_office}}, উপজেলা {{address.upazila}}, জেলা '
             '{{address.district}} — ইলমে দ্বীন শিক্ষার উদ্দেশ্যে আপনার মাদরাসার '
             'সকল নিয়ম কানুন মেনে {{class.applied_for}} শ্রেণিতে ভর্তি হতে ইচ্ছুক।'),
    'text_bn': ('বিনীত নিবেদন এই যে, আমি {{student.name_bn}} ইবনে/বিনতে '
                '{{guardian.father_name_bn}}, গ্রাম {{address.village}}, ডাকঘর '
                '{{address.post_office}}, উপজেলা {{address.upazila}}, জেলা '
                '{{address.district}} — ইলমে দ্বীন শিক্ষার উদ্দেশ্যে আপনার মাদরাসার '
                'সকল নিয়ম কানুন মেনে {{class.applied_for}} শ্রেণিতে ভর্তি হতে ইচ্ছুক।'),
}

LETTER_CLOSING = {
    'type': 'prose',
    'indent': True,
    'text': ('অতএব, মহোদয়ের নিকট আকুল আবেদন এই যে, আমাকে উক্ত শ্রেণিতে ভর্তি করে '
             'দ্বীনি শিক্ষা অর্জনের সুযোগ দানে বাধিত করবেন।'),
    'text_bn': ('অতএব, মহোদয়ের নিকট আকুল আবেদন এই যে, আমাকে উক্ত শ্রেণিতে ভর্তি করে '
                'দ্বীনি শিক্ষা অর্জনের সুযোগ দানে বাধিত করবেন।'),
}

APPLICANT_SIGNATURE = {
    'type': 'signature_row',
    'captions': ['আবেদনকারীর স্বাক্ষর'],
    'align': 'right',
}

# আবেদনকারীর তথ্যাবলী — the two-column grid of the scanned form, in its order.
FIELD_GRID = {
    'type': 'field_grid',
    'title': "Applicant's particulars",
    'title_bn': 'আবেদনকারীর তথ্যাবলী',
    'columns': 2,
    'fields': [
        {'label': 'Name', 'label_bn': 'নাম', 'value': '{{student.name_bn}}'},
        {'label': 'Date of birth', 'label_bn': 'জন্ম তারিখ', 'value': '{{student.dob}}'},
        {'label': "Father's name", 'label_bn': 'পিতার নাম',
         'value': '{{guardian.father_name_bn}}'},
        {'label': "Mother's name", 'label_bn': 'মাতার নাম',
         'value': '{{guardian.mother_name_bn}}'},
        {'label': 'Village', 'label_bn': 'গ্রাম-মহল্লা', 'value': '{{address.village}}'},
        {'label': 'Post office', 'label_bn': 'ডাকঘর', 'value': '{{address.post_office}}'},
        {'label': 'Upazila', 'label_bn': 'উপজেলা', 'value': '{{address.upazila}}'},
        {'label': 'District', 'label_bn': 'জেলা', 'value': '{{address.district}}'},
        {'label': 'Mobile', 'label_bn': 'মোবাইল নম্বর', 'value': '{{guardian.phone}}'},
        {'label': 'Birth certificate no', 'label_bn': 'জন্ম নিবন্ধন নম্বর',
         'value': '{{student.birth_certificate_no}}'},
    ],
}

QUESTION_SET = {
    'type': 'question_set',
    'section': 'admission',
    'title': 'Other information',
    'title_bn': 'অন্যান্য তথ্য',
}

# অফিস কর্তৃক পূরণীয় — printed as blank rules in BOTH modes. It is filled by
# hand after the interview, so there is nothing for the system to resolve into
# it; what it needs is the labels, so whoever writes on it knows which line is
# প্রাপ্ত নম্বর.
OFFICE_BOX = {
    'type': 'office_box',
    'title': 'For office use',
    'title_bn': 'অফিস কর্তৃক পূরণীয়',
    'panels': [
        {'title': 'Existing student', 'title_bn': 'পুরাতন শিক্ষার্থী',
         'lines': ['ফলাফল', 'প্রাপ্ত নম্বর', 'গড় নম্বর', 'বিভাগ', 'শ্রেণি']},
        {'title': 'New student', 'title_bn': 'নতুন শিক্ষার্থী',
         'lines': ['পরীক্ষক', 'পরীক্ষকের মন্তব্য', 'প্রাপ্ত নম্বর',
                   'উপযুক্ত জামাত/বিভাগ']},
    ],
    'lines': [
        'উক্ত শিক্ষার্থীকে ................ শ্রেণিতে ভর্তির অনুমতি দেওয়া হলো',
        'মন্তব্য',
    ],
}

OFFICE_SIGNATURE = {
    'type': 'signature_row',
    'captions': ['নাযেমে তালীমাত', 'মুহতামিম'],
}

# ─────────────────────────────────────────────────────────────────────────────
# Page 2 — the two pledge lists
# ─────────────────────────────────────────────────────────────────────────────

UNDERTAKING = {
    'type': 'bullet_list',
    'style': 'number',
    'title': "Student's undertaking",
    'title_bn': 'ভর্তিচ্ছুক শিক্ষার্থীর অঙ্গিকারনামা',
    'items': [
        'আমি একমাত্র আল্লাহ তাআলার সন্তুষ্টির উদ্দেশ্যে ইলমে দ্বীন অর্জনের নিয়্যতে '
        'এই প্রতিষ্ঠানে ভর্তি হচ্ছি।',
        'আমি আহলে সুন্নাত ওয়াল জামাআতের আকীদা-বিশ্বাস অনুযায়ী চলব এবং তার '
        'বিরোধী কোনো মত ও পথ গ্রহণ করব না।',
        'মাদরাসার অনুমতি ছাড়া আমি কোথাও যাব না এবং ছুটি ব্যতীত মাদরাসা ত্যাগ করব না।',
        'আমি উস্তাদগণের আদব রক্ষা করব এবং তাঁদের প্রতিটি নির্দেশ মেনে চলব।',
        'মাদরাসার সকল আসবাবপত্র ও সম্পদের যথাযথ হেফাজত করব; ক্ষতি করলে ক্ষতিপূরণ দেব।',
        'টেলিভিশন, সিনেমা, অশ্লীল ম্যাগাজিন ও প্রাণীর ছবি তোলা থেকে বিরত থাকব।',
        'মোবাইল ফোনসহ নিষিদ্ধ কোনো বস্তু মাদরাসায় রাখব না।',
        'প্রতিটি পরীক্ষায় অংশগ্রহণ করব; বিনা কারণে অনুপস্থিত থাকব না।',
        'নিয়ম ভঙ্গের কারণে কর্তৃপক্ষ আমাকে বহিষ্কার করলে আমার বা আমার অভিভাবকের '
        'কোনো আপত্তি থাকবে না।',
        'উপরোক্ত সকল নিয়ম-কানুন আমি স্বেচ্ছায় মেনে নিয়ে অঙ্গিকারনামায় স্বাক্ষর করছি।',
    ],
}

UNDERTAKING_SIGNATURE = {
    'type': 'signature_row',
    'captions': ['আবেদনকারীর স্বাক্ষর'],
    'align': 'right',
}

GUARDIAN_RULES = {
    'type': 'bullet_list',
    'style': 'number',
    'title': "Guardian's rules",
    'title_bn': 'অভিভাবকের পালনীয় নিয়মাবলী',
    'items': [
        'ছুটির দিনে নির্ধারিত সময়ের মধ্যে সন্তানকে নিয়ে যেতে ও পৌঁছে দিতে হবে।',
        'ছুটির প্রয়োজন হলে অভিভাবককে লিখিত দরখাস্ত দিয়ে অনুমতি নিতে হবে।',
        'পারিবারিক অনুষ্ঠানের জন্য শিক্ষাবর্ষের মাঝে ছুটি নেওয়া যাবে না।',
        'কোনো অভিযোগ থাকলে তা সরাসরি মুহতামিম সাহেবকে জানাতে হবে; '
        'উস্তাদের সাথে বাকবিতণ্ডা করা যাবে না।',
        'অভিভাবক শ্রেণিকক্ষে প্রবেশ করতে পারবেন না।',
        'প্রতি পরীক্ষার ফলাফলপত্রে স্বাক্ষর করে যথাসময়ে ফেরত দিতে হবে।',
        'বছরে বারো মাসের বেতন পরিশোধ করতে হবে; ছুটির মাসও এর অন্তর্ভুক্ত।',
        'প্রতি মাসের ৭ তারিখের মধ্যে বেতন ও অন্যান্য পাওনা পরিশোধ করতে হবে।',
        'সন্তানের দ্বারা মাদরাসার কোনো ক্ষতি হলে তার দায়ভার অভিভাবককে বহন করতে হবে।',
        'সাক্ষাতের নির্ধারিত দিন ও সময় ছাড়া সন্তানের সাথে সাক্ষাৎ করা যাবে না।',
        'আমি আমার সন্তান {{student.name_bn}} -এর অভিভাবক হিসেবে উপরোক্ত সকল '
        'নিয়ম মেনে চলার অঙ্গিকার করছি।',
    ],
}

GUARDIAN_SIGNATURE = {
    'type': 'signature_row',
    'captions': ['তারিখ: {{form.date}}', 'অভিভাবকের স্বাক্ষর'],
}

# The block order docs/07 §3 specifies for the reference form.
MADRASAH_ADMISSION_BLOCKS = [
    LETTERHEAD,
    META_ROW,
    TITLE,
    LETTER_HEAD_LINES,
    SUBJECT_LINE,
    LETTER_BODY,
    LETTER_CLOSING,
    APPLICANT_SIGNATURE,
    {'type': 'divider'},
    FIELD_GRID,
    QUESTION_SET,
    OFFICE_BOX,
    OFFICE_SIGNATURE,
    {'type': 'page_break'},
    UNDERTAKING,
    UNDERTAKING_SIGNATURE,
    {'type': 'spacer', 'height': '8mm'},
    GUARDIAN_RULES,
    GUARDIAN_SIGNATURE,
]

FORM_TEMPLATE_SEEDS = {
    'madrasah': [
        {
            'name': 'Admission form',
            'name_bn': 'ভর্তি ফরম',
            'form_type': 'admission',
            'paper': 'A4',
            'margins': '12mm 14mm',
            'is_default': True,
            'blocks': MADRASAH_ADMISSION_BLOCKS,
        },
    ],
}

# The three standard questions of the scanned form. Two of them bind to a
# student field with `maps_to` (§5.2) — "previous institution" and "previous
# class" are student data that happens to be asked on a form, and storing them
# as answers as well would give a report two sources that disagree within a
# month. The third is a genuine form answer with nowhere else to live.
QUESTION_SEEDS = {
    'madrasah': [
        {
            'section': 'admission',
            'text': 'Which institution did the applicant previously attend?',
            'text_bn': 'পূর্বে কোন প্রতিষ্ঠানে পড়েছে',
            'type': 'short_text',
            'print_style': 'inline',
            'maps_to': 'previous_institution',
            'order': 10,
        },
        {
            'section': 'admission',
            'text': 'In which class?',
            'text_bn': 'কোন শ্রেণিতে পড়েছে',
            'type': 'short_text',
            'print_style': 'inline',
            'maps_to': 'previous_class',
            'order': 20,
        },
        {
            'section': 'admission',
            'text': 'Which class does the applicant wish to join?',
            'text_bn': 'কোন শ্রেণিতে ভর্তি হতে ইচ্ছুক',
            'type': 'short_text',
            'print_style': 'inline',
            'order': 30,
        },
    ],
}
