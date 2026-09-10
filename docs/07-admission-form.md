# 07 — Printable Admission Form

Generating the ভর্তি ফরম after a student admission is filled in — a two-page
A4 document with the institution's identity, a prose application letter whose
blanks are filled from the student's record, a configurable question set,
undertaking pledges, office-use panels and signature lines.

**Reference:** `~/Downloads/admission form demo/` — the two scanned pages of
Islamic Education Center Dasherbari's existing printed form. The design below
reproduces that layout exactly and makes every part of it editable per branch.

**Scope:** V1. It belongs with Admissions (Phase 2), because a madrasah that
cannot print its admission form cannot use the system for admissions at all.

---

## 1. What the printed form contains

Read from the reference scans, top to bottom.

### Page 1 — ভর্তি ফরম

| Band | Contents | Filled by |
|------|----------|-----------|
| **Letterhead** | Logo · Arabic name (مركز التعليم الاسلامي داشرباري) · English name · Bangla name · স্থাপিত: ১৯৮৫ ইং · address line | Branch config |
| **Meta row** | ফরম নং · নতুন/পুরাতন · ভর্তি নং · তারিখ · ☑ আবাসিক ☐ অনাবাসিক | System |
| **Application letter** | মাননীয় মুহতামিম সাহেব → বিষয়: ভর্তির জন্য আবেদন → **"বিনীত নিবেদন এই যে, আমি ⎯⎯⎯ ইবনে/বিনতে ⎯⎯⎯ ইলমে দ্বীন শিক্ষার উদ্দেশ্যে আপনার মাদরাসার সকল নিয়ম কানুন মেনে ভর্তি হতে ইচ্ছুক।"** → অতএব… paragraph → আবেদনকারীর স্বাক্ষর | **Prose with inline blanks, filled from the student record** |
| **আবেদনকারীর তথ্যাবলী** | Two-column grid: নাম / জন্ম তারিখ · পিতার নাম / মাতার নাম · গ্রাম-মহল্লা / ডাকঘর · উপজেলা / জেলা · মোবাইল নম্বর | Student record |
| **Questions** | পূর্বে কোন প্রতিষ্ঠানে পড়েছে · কোন শ্রেণিতে · কোন শ্রেণিতে ভর্তি হতে ইচ্ছুক | **Question set** |
| **অফিস কর্তৃক পূরণীয়** | Two panels — *পুরাতন শিক্ষার্থী* (ফলাফল, প্রাপ্ত নম্বর, গড় নম্বর, বিভাগ, শ্রেণি) and *নতুন শিক্ষার্থী* (পরীক্ষক, পরীক্ষকের মন্তব্য, প্রাপ্ত নম্বর, উপযুক্ত জামাত/বিভাগ) · then the two admission-decision lines with নাযেমে তালীমাত and মুহতামিম signatures | **Left blank — filled by hand after the interview** |

### Page 2 — অঙ্গিকারনামা and নিয়মাবলী

| Band | Contents |
|------|----------|
| **ভর্তিচ্ছুক শিক্ষার্থীর অঙ্গিকারনামা** | ~10 bulleted pledges (intention of study, aqidah, not leaving without permission, respect for teachers, care of property, abstaining from television/magazines/photography, exam requirement, no objection to expulsion, obedience to rules, final declaration) → **আবেদনকারীর স্বাক্ষর** |
| **অভিভাবকের পালনীয় নিয়মাবলী** | ~11 bulleted rules for the guardian (collection at holidays, leave applications, family events, complaints go to the Muhtamim, no entering classrooms, signing the progress report, 12 months' fees, payment by the 7th, liability, visiting hours) → last bullet carries a blank for the child's name → **তারিখ** and **অভিভাবকের স্বাক্ষর** |

---

## 2. The design decision that shapes everything

**The form is a template of ordered blocks, not a hard-coded page.**

Every madrasah's form differs — different pledges, different Arabic name, a
different office panel, different questions. Hard-coding this one institution's
form means the next branch needs a developer. So:

- A **`FormTemplate`** holds an ordered list of **blocks**.
- Each block has a **type** that determines how it renders.
- **Prose blocks carry placeholders** that resolve against the student record.
- **Question blocks** pull from the `Question` model.
- Everything printed is either template text, a resolved placeholder, an answer,
  or a deliberate blank.

The result: an admin edits the pledge list in a textarea and the printed form
changes. No deploy.

---

## 3. Block types

| Type | Renders | Configurable |
|------|---------|--------------|
| `letterhead` | Logo, Arabic / English / Bangla names, established year, address | From `Branch`; overridable per template |
| `meta_row` | Form no · new/old · admission no · date · residential checkbox | Which fields appear |
| `prose` | A paragraph with inline blanks — §4 | The text itself, both languages |
| `field_grid` | Two-column labelled grid of student data | Which fields, in what order, labels |
| `question_set` | The questions of one section — §5 | Which section |
| `bullet_list` | Numbered or bulleted pledges / rules | The list items, both languages |
| `office_box` | A bordered panel of blank ruled lines | Title, sub-panels, line labels |
| `signature_row` | One or more signature lines with captions | Captions, count, alignment |
| `spacer` / `divider` | Vertical space, a rule | Height |
| `page_break` | Forces the next A4 page | — |

The reference form is: `letterhead · meta_row · prose · prose · signature_row ·
field_grid · question_set · office_box · page_break · bullet_list ·
signature_row · bullet_list · signature_row`.

---

## 4. Prose placeholders — the fill-in-the-blank line

The line the brief describes —

> বিনীত নিবেদন এই যে, আমি ⎯⎯⎯⎯⎯ ইবনে/বিনতে ⎯⎯⎯⎯⎯ ইলমে দ্বীন শিক্ষার উদ্দেশ্যে…

is stored as template text with placeholders:

```
বিনীত নিবেদন এই যে, আমি {{student.name_bn}} ইবনে/বিনতে {{guardian.father_name_bn}}
ইলমে দ্বীন শিক্ষার উদ্দেশ্যে আপনার মাদরাসার সকল নিয়ম কানুন মেনে ভর্তি হতে ইচ্ছুক।
```

**Rendering rules:**

- A resolved placeholder prints **underlined, in the filled style** — so a
  printed form still reads as a form, with the answer sitting on the rule.
- An **unresolved or empty** placeholder prints as a **blank rule of the same
  width**, ready to be written on by hand. This is what makes one template serve
  both purposes (§7).
- Unknown placeholder names are a **validation error when the template is
  saved**, never a silent blank at print time. The editor offers the list.

**Available placeholders** (the closed set, validated on save):

| Group | Names |
|-------|-------|
| Institution | `branch.name`, `branch.name_bn`, `branch.name_ar`, `branch.address_bn`, `branch.established_year`, `branch.head_title` |
| Form | `form.form_no`, `form.date`, `form.admission_no`, `form.session`, `form.is_residential`, `form.is_new_student` |
| Student | `student.name`, `student.name_bn`, `student.dob`, `student.gender`, `student.mobile`, `student.photo`, `student.birth_certificate_no` |
| Guardian | `guardian.father_name_bn`, `guardian.mother_name_bn`, `guardian.phone`, `guardian.occupation`, `guardian.nid` |
| Address | `address.village`, `address.post_office`, `address.upazila`, `address.district` |
| Academic | `class.name_bn`, `class.applied_for`, `previous.institution`, `previous.class` |

> **Address needs splitting.** The reference form asks for গ্রাম/মহল্লা · ডাকঘর ·
> উপজেলা · জেলা as four separate boxes. `docs/03` currently has
> `present_address` as one Text field, which cannot fill four boxes. **Change:**
> add `village`, `post_office`, `upazila`, `district` as structured fields on
> `Student`, keeping the free-text field for anything extra. This also makes
> "students from this upazila" a query instead of a text search.

---

## 5. The Question model

The brief asks for questions with **multiple choice, single choice and
description** types. These are the form's variable part — what an institution
asks beyond the fixed identity fields.

### `Question` **[BS]**

| Field | Type | Notes |
|-------|------|-------|
| `branch` | → Branch | |
| `template` | → FormTemplate, null | Null ⇒ reusable across templates |
| `section` | Char | Groups questions into a `question_set` block |
| `text`, `text_bn` | Char(300) | The question as printed |
| `type` | Char choices | `single_choice` · `multi_choice` · `description` · `short_text` · `number` · `date` · `yes_no` |
| `options` | JSON list | `[{value, label, label_bn}]` — required for the choice types, ignored otherwise |
| `is_required` | Bool | Enforced on the data-entry screen, not on the printed page |
| `print_style` | Char | `inline` (label and rule on one line) · `block` (label above, ruled lines below) · `checkbox` (choices as ☐ boxes) |
| `answer_lines` | Int | For `description` — how many ruled lines to print |
| `maps_to` | Char, blank | Optional binding to a student field, §5.2 |
| `order` | Int | |
| `is_active` | Bool | |

### 5.1 How each type prints

```
single_choice, print_style=checkbox     ☐ আবাসিক    ☑ অনাবাসিক
single_choice, print_style=inline       কোন শ্রেণিতে ভর্তি হতে ইচ্ছুক : ⎯⎯⎯⎯⎯⎯⎯⎯
multi_choice                            ☐ কুরআন  ☐ হাদীস  ☐ ফিকহ   (several may be ticked)
description                             পূর্ব অভিজ্ঞতা :
                                        ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯
                                        ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯
short_text / number / date              পূর্বে কোন প্রতিষ্ঠানে পড়েছে : ⎯⎯⎯⎯⎯⎯⎯
```

When an answer exists it is printed on the rule; when it does not, the rule
prints empty.

### 5.2 `maps_to` — the anti-duplication rule

A question whose answer is really a student field (previous institution,
residential yes/no) sets `maps_to='previous_institution'`. Answering it writes
the student field; the answer is **not** stored twice.

Without this, "previous institution" ends up in both `Student` and
`AdmissionAnswer`, they disagree within a month, and no report can be trusted.
**A question either maps to a field or stores an answer — never both.**

### `AdmissionAnswer` **[BS]**

| `branch`, `admission` → Admission, `question` → Question, `value` (JSON), `answered_at` |

`value` is JSON so one column serves every type: `"খারিজি"` for text, `["quran",
"hadith"]` for multi-choice, `true` for yes/no. `unique_together (admission, question)`.

Only questions **without** `maps_to` create rows here.

---

## 6. Models added by this feature

Four, all V1, all branch-scoped:

| Model | Purpose |
|-------|---------|
| `FormTemplate` | branch · name · form_type (`admission` / `undertaking` / `id_card` / `certificate`) · `blocks` (JSON, ordered) · `paper` (A4/Legal) · `margins` · `is_default` · `is_active` |
| `Question` | §5 |
| `AdmissionAnswer` | §5.2 |
| `PrintedForm` | branch · admission · template · `form_no` · `snapshot` (JSON) · printed_by · printed_at · reprint_count |

**`PrintedForm.snapshot` is the important one.** It stores the fully resolved
form — every placeholder value and answer as it stood at print time. A form
reprinted in three years must show what was signed, not what the record says
today after a name correction. Same reasoning as storing `Result` rows rather
than recomputing them (`docs/03` §9).

`form_no` is its own per-branch gapless sequence, separate from the admission
number — the reference form prints both (ফরম নং and ভর্তি নং), because forms are
issued before admission numbers exist.

### 6.1 Blocks as JSON, not as rows

`FormTemplate.blocks` is an ordered JSON list rather than a `FormBlock` table.
Blocks are only ever read as a whole document, always in order, and never
queried individually — a table would buy joins and reordering pain for nothing.
The JSON is schema-validated on save so a malformed block cannot reach the
renderer.

---

## 7. One template, two outputs

| Output | When | How |
|--------|------|-----|
| **Blank form** | Printed in a stack and handed to walk-in applicants | Render with an empty context — every placeholder becomes a rule |
| **Filled form** | After data entry, for signing and filing | Render with the admission's data |

Both come from the same template, so the two can never drift. This matters:
madrasahs print blank forms in bulk at admission season and fill them by hand,
then enter the data afterwards. Supporting only the filled case would mean the
printed stack came from a different Word file, and the printed stack is the one
the guardian signs.

---

## 8. Rendering

**HTML + CSS print, rendered in the browser.** Not a PDF library, for V1.

```
GET /api/admissions/{id}/form/?template=<id>&mode=filled|blank
   → HTML document, print-ready
```

The SPA opens it and calls `window.print()`. Reasons this beats a PDF library
here:

1. **Bangla and Arabic shaping is the whole problem.** Browsers do complex-script
   layout correctly and for free. Python PDF libraries need font configuration
   and still break ligatures — and this form has both Bangla and Arabic on the
   letterhead.
2. Editing a template is instant feedback in a preview pane.
3. No new dependency.

CSS carries the print discipline:

```css
@page { size: A4; margin: 12mm 14mm; }
@media print {
  .page-break { break-before: page; }
  .no-print   { display: none; }
  .office-box { break-inside: avoid; }
}
```

Fonts are **self-hosted and embedded**, never a Google Fonts link — a form must
print correctly on a school computer with no internet. A Bangla face
(SolaimanLipi / Kalpurush) and an Arabic face (Amiri / Scheherazade) ship in
`frontend/admin_dashboard/public/fonts/`.

**Server-side PDF is V2** — needed only for bulk generation and archiving, at
which point WeasyPrint renders the same HTML.

---

## 9. Where it appears in the UI

| Screen | Action |
|--------|--------|
| Admissions → application detail | **Print form** → preview → print. Also **Print blank form** |
| Admissions → list | Multi-select → print several filled forms in one job |
| Settings → **Form templates** | List, duplicate, edit blocks, live A4 preview beside the editor |
| Settings → **Questions** | The question bank, per section, drag to reorder |
| Student detail → Documents | Every `PrintedForm` for that student, reprintable from its snapshot |

The template editor is a block list with an add-block menu and a preview pane —
not a WYSIWYG page designer. A madrasah admin needs to change the pledge text
and the questions, not drag text boxes to arbitrary coordinates.

---

## 10. Seeding

`branches.services.create_branch()` already seeds fee, income and expense categories
(`docs/03` §1). **It also seeds a default `admission` FormTemplate reproducing
the reference form** — letterhead, the বিনীত নিবেদন letter, the তথ্যাবলী grid, the
three standard questions, the office panel, and both page-2 bullet lists with
their standard Bangla text.

A new branch therefore prints a usable, correct admission form on day one, and
edits the pledge wording only if it wants to. That is the same principle as the
seeded fee categories: the system arrives knowing how a Bangladeshi madrasah
works, rather than asking the admin to teach it.

---

## 11. Changes this feature makes to earlier docs

| Doc | Change |
|-----|--------|
| `03-database.md` §4 | `Student` gains `village`, `post_office`, `upazila`, `district`; free-text address stays for extras |
| `03-database.md` | New app `forms/`: `FormTemplate`, `Question`, `AdmissionAnswer`, `PrintedForm` |
| `01-architecture.md` §6 | `forms/` added to the app list; depends on `branches` + `students`, imported by none |
| `05-scope-and-v1.md` §6 | V1 table count rises from 19 to **23** |
| `05-scope-and-v1.md` §8 | Phase 2 gains the form renderer and template seeding |
| `02-system-design.md` §4.1 | Admission workflow gains: print blank → fill by hand → enter data → print filled → sign → file |
| `CLAUDE.md` | `forms/` in the layout; fonts in `public/fonts/` |

`Branch` also gains `name_ar` and `established_year` for the letterhead.
