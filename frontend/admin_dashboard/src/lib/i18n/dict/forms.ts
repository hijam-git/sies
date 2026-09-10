// Bangla for the printable admission form — the preview, the template block
// editor and the question bank (`docs/07`).
//
// This module's screens print a Bangladeshi madrasah's legal-ish document, so
// the office's own words are used rather than translations of the English:
// ফরম নং for the form number, অঙ্গিকারনামা for the pledge page, পূরণীয় for what
// is filled in by hand. An administrator editing the pledge text should read
// this screen in the same words that appear on the paper in front of them.
const forms: Record<string, string> = {
  // ── Printing ───────────────────────────────────────────────────────────
  'Print': 'প্রিন্ট',
  'Print form': 'ফরম প্রিন্ট',
  'Print blank form': 'খালি ফরম প্রিন্ট',
  'Print selected forms': 'নির্বাচিত ফরম প্রিন্ট',
  'Admission form': 'ভর্তি ফরম',
  'Admission forms': 'ভর্তি ফরম',
  'Blank admission form': 'খালি ভর্তি ফরম',
  'Form preview': 'ফরমের প্রিভিউ',
  'Preparing the form…': 'ফরম তৈরি হচ্ছে…',
  'Could not produce this form.': 'এই ফরমটি তৈরি করা যায়নি।',
  'A4 · 210 × 297 mm': 'এ৪ · ২১০ × ২৯৭ মিমি',
  'Zoom in': 'বড় করুন',
  'Zoom out': 'ছোট করুন',
  'Select': 'নির্বাচন',
  'Select all on this page': 'এই পাতার সব নির্বাচন করুন',
  'selected': 'টি নির্বাচিত',
  'Form template': 'ফরম টেমপ্লেট',
  'The default form': 'ডিফল্ট ফরম',
  'This copy is recorded and given a form number. Reprint it later from the student’s Documents.':
    'এই কপিটি সংরক্ষিত হয় এবং একটি ফরম নং পায়। পরে শিক্ষার্থীর কাগজপত্র থেকে পুনর্মুদ্রণ করা যাবে।',
  'Each of these is recorded and given its own form number.':
    'প্রতিটি কপি সংরক্ষিত হয় এবং আলাদা ফরম নং পায়।',
  'A blank form to print in a stack and fill in by hand. Nothing is recorded and no form number is issued.':
    'হাতে পূরণ করার জন্য খালি ফরম — একসাথে অনেক কপি ছাপার জন্য। কিছু সংরক্ষিত হয় না, ফরম নংও দেওয়া হয় না।',

  // ── Printed forms on the student record ────────────────────────────────
  'Printed forms': 'মুদ্রিত ফরম',
  'Printed form': 'মুদ্রিত ফরম',
  'Reprints': 'পুনর্মুদ্রণ',
  'Reprint from the snapshot': 'সংরক্ষিত কপি থেকে পুনর্মুদ্রণ',
  'No form has been printed for this student yet.':
    'এই শিক্ষার্থীর জন্য এখনো কোনো ফরম প্রিন্ট করা হয়নি।',
  'Could not load the printed forms.': 'মুদ্রিত ফরমের তালিকা আনা যায়নি।',
  'This is the form exactly as it was printed and signed — not the record as it stands today.':
    'যেভাবে ফরমটি ছাপা ও স্বাক্ষরিত হয়েছিল ঠিক সেভাবেই — আজকের রেকর্ড অনুযায়ী নয়।',
  'A reprint shows what was signed at the time. To print today’s details, use Print form on the application.':
    'পুনর্মুদ্রণে সেদিনের স্বাক্ষরিত তথ্যই আসে। আজকের তথ্য ছাপতে আবেদনের পাশে “ফরম প্রিন্ট” ব্যবহার করুন।',

  // ── Template list ──────────────────────────────────────────────────────
  'Template': 'টেমপ্লেট',
  'Templates': 'টেমপ্লেট',
  'Blocks': 'ব্লক',
  'Default': 'ডিফল্ট',
  'Make default': 'ডিফল্ট করুন',
  'Duplicate': 'কপি করুন',
  'Edit blocks': 'ব্লক সম্পাদনা',
  'View blocks': 'ব্লক দেখুন',
  'Back to the list': 'তালিকায় ফিরুন',
  'No form templates yet.': 'এখনো কোনো ফরম টেমপ্লেট নেই।',
  'Could not load the form templates.': 'ফরম টেমপ্লেট আনা যায়নি।',
  'Could not save this form template.': 'এই ফরম টেমপ্লেট সংরক্ষণ করা যায়নি।',
  'Could not copy this form template.': 'এই ফরম টেমপ্লেট কপি করা যায়নি।',
  'Could not set the default form.': 'ডিফল্ট ফরম নির্ধারণ করা যায়নি।',
  'The printed forms this institution issues. Editing the pledge text here changes what prints — no developer, no deploy.':
    'এই প্রতিষ্ঠান যেসব ফরম ছাপে। এখানে অঙ্গিকারনামার লেখা বদলালেই ছাপার ফরম বদলে যায় — কোনো ডেভেলপার লাগে না।',
  'An ordered list of blocks. This is what prints, top to bottom.':
    'ব্লকের ক্রমিক তালিকা। উপর থেকে নিচে ঠিক এভাবেই ছাপা হয়।',
  'Save and refresh the preview': 'সংরক্ষণ করে প্রিভিউ হালনাগাদ করুন',
  'The preview shows the saved template, rendered by the server — blank, the way the stack is printed.':
    'প্রিভিউতে সংরক্ষিত টেমপ্লেটটি সার্ভার থেকেই আসে — খালি অবস্থায়, যেভাবে স্তূপ করে ছাপা হয়।',
  'One block was rejected. It is marked below.': 'একটি ব্লক গ্রহণ করা যায়নি। নিচে সেটি চিহ্নিত।',
  'Paper': 'কাগজ',
  'Margins': 'মার্জিন',

  // ── The block editor ───────────────────────────────────────────────────
  'Add a block': 'ব্লক যোগ করুন',
  'This template has no blocks yet.': 'এই টেমপ্লেটে এখনো কোনো ব্লক নেই।',
  'This block has nothing to configure.': 'এই ব্লকে সেট করার কিছু নেই।',
  'Letterhead': 'লেটারহেড',
  'The institution’s Arabic, Bangla and English names, and its address.':
    'প্রতিষ্ঠানের আরবি, বাংলা ও ইংরেজি নাম এবং ঠিকানা।',
  'Form number row': 'ফরম নং সারি',
  'Form no · admission no · session · date, across one line.':
    'ফরম নং · ভর্তি নং · শিক্ষাবর্ষ · তারিখ — এক লাইনে।',
  'Paragraph': 'অনুচ্ছেদ',
  'Template text with fill-in-the-blank placeholders — the application letter.':
    'ফাঁকা ঘরসহ লেখা — আবেদনপত্রের ভাষা।',
  'Field grid': 'তথ্যছক',
  'A two-column labelled grid of the applicant’s details.':
    'আবেদনকারীর তথ্যের দুই কলামের ছক।',
  'Questions': 'প্রশ্নাবলী',
  'Prints one section of the question bank.': 'প্রশ্নভাণ্ডারের একটি অংশ ছাপে।',
  'Bulleted list': 'তালিকা',
  'The pledges and the guardian’s rules.': 'অঙ্গিকারনামা ও অভিভাবকের নিয়মাবলী।',
  'Office-use panel': 'অফিস কর্তৃক পূরণীয় ঘর',
  'A bordered box of blank ruled lines, filled in by hand after the interview.':
    'বর্ডার দেওয়া খালি ঘর — সাক্ষাৎকারের পর হাতে পূরণ করা হয়।',
  'Signature line': 'স্বাক্ষরের ঘর',
  'One or more signature spaces with captions under them.':
    'নিচে ক্যাপশনসহ এক বা একাধিক স্বাক্ষরের জায়গা।',
  'Space': 'ফাঁকা জায়গা',
  'Vertical space.': 'উল্লম্ব ফাঁকা জায়গা।',
  'Rule': 'দাগ',
  'A horizontal line.': 'একটি আড়াআড়ি রেখা।',
  'Page break': 'নতুন পাতা',
  'Everything after this starts on the next sheet.': 'এর পরের সবকিছু পরের পাতায় ছাপা হবে।',
  'Arabic lines': 'আরবি লাইন',
  'Lines': 'লাইনসমূহ',
  'Show the logo': 'লোগো দেখান',
  'Add line': 'লাইন যোগ করুন',
  'Add field': 'ঘর যোগ করুন',
  'Printed label': 'ছাপার লেখা',
  'Insert a placeholder': 'প্লেসহোল্ডার বসান',
  'Printed text (Bangla)': 'ছাপার লেখা (বাংলা)',
  'A placeholder that has no value prints as a blank rule to write on.':
    'যে প্লেসহোল্ডারের তথ্য নেই তা হাতে লেখার জন্য ফাঁকা দাগ হয়ে ছাপে।',
  'English text': 'ইংরেজি লেখা',
  'The editor’s reference. The Bangla is what prints.':
    'সম্পাদকের জন্য। ছাপা হয় বাংলাটাই।',
  'Alignment': 'অবস্থান',
  'Left': 'বামে',
  'Centre': 'মাঝে',
  'Right': 'ডানে',
  'Indent the first line': 'প্রথম লাইনে ফাঁক দিন',
  'Title (Bangla)': 'শিরোনাম (বাংলা)',
  'Columns': 'কলাম',
  'Prints every active question of the question bank in this section.':
    'এই অংশের সক্রিয় সব প্রশ্ন ছাপে।',
  'Marker': 'চিহ্ন',
  'Bullets': 'বুলেট',
  'Numbers': 'সংখ্যা',
  'None': 'কিছু না',
  'Items': 'আইটেম',
  'items': 'টি আইটেম',
  'Ruled lines': 'দাগ কাটা লাইন',
  'Panels': 'ঘর',
  'Panel title (Bangla)': 'ঘরের শিরোনাম (বাংলা)',
  'Add panel': 'ঘর যোগ করুন',
  'Remove panel': 'ঘর সরান',
  'Captions': 'ক্যাপশন',
  'Spread across the page': 'পাতাজুড়ে ছড়িয়ে',
  'Height': 'উচ্চতা',

  // ── The question bank ──────────────────────────────────────────────────
  'New question': 'নতুন প্রশ্ন',
  'Edit question': 'প্রশ্ন সম্পাদনা',
  'Add to this section': 'এই অংশে যোগ করুন',
  'No questions yet.': 'এখনো কোনো প্রশ্ন নেই।',
  'Could not load the questions.': 'প্রশ্নগুলো আনা যায়নি।',
  'Could not save this question.': 'এই প্রশ্নটি সংরক্ষণ করা যায়নি।',
  'Could not delete this question.': 'এই প্রশ্নটি মুছে ফেলা যায়নি।',
  'Could not save the new order.': 'নতুন ক্রম সংরক্ষণ করা যায়নি।',
  'What the form asks beyond name and address. Each section prints as one block of the template.':
    'নাম-ঠিকানার বাইরে ফরম যা যা জিজ্ঞাসা করে। প্রতিটি অংশ টেমপ্লেটের একটি ব্লক হয়ে ছাপে।',
  'Question (Bangla)': 'প্রশ্ন (বাংলা)',
  'Question (English)': 'প্রশ্ন (ইংরেজি)',
  'Short text': 'সংক্ষিপ্ত উত্তর',
  'Description': 'বর্ণনা',
  'Single choice': 'একটি বাছাই',
  'Multiple choice': 'একাধিক বাছাই',
  'Yes / no': 'হ্যাঁ / না',
  'Print style': 'ছাপার ধরন',
  'Label and rule on one line': 'লেখা ও দাগ এক লাইনে',
  'Label above, ruled lines below': 'উপরে লেখা, নিচে দাগ',
  'Choices as ☐ boxes': '☐ ঘর হিসেবে বিকল্প',
  'Ruled lines to print': 'কয়টি দাগ ছাপবে',
  'Every template': 'সব টেমপ্লেট',
  'Leave blank and every form of this institution may ask it.':
    'খালি রাখলে প্রতিষ্ঠানের যেকোনো ফরমে এটি ব্যবহার করা যাবে।',
  'Writes this student field': 'যে ফিল্ডে উত্তর লেখা হবে',
  'Stores its own answer': 'নিজেই উত্তর সংরক্ষণ করবে',
  'A question bound to a field writes it and stores no separate answer, so the two can never disagree.':
    'কোনো ফিল্ডের সাথে যুক্ত প্রশ্ন সেই ফিল্ডেই লেখে, আলাদা উত্তর রাখে না — তাই দুই জায়গায় দুই তথ্য হওয়ার সুযোগ নেই।',
  'Writes': 'লেখে',
  'Options': 'বিকল্প',
  'Add option': 'বিকল্প যোগ করুন',
  'Printed label (Bangla)': 'ছাপার লেখা (বাংলা)',
  'Stored value': 'সংরক্ষিত মান',
  'Required on the data-entry screen': 'তথ্য এন্ট্রির সময় আবশ্যক',
  'Prints on the form': 'ফরমে ছাপা হবে',
  'Inactive': 'নিষ্ক্রিয়',
};

export default forms;
