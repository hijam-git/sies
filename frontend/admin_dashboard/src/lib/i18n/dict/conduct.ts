// Bangla for the observation register — নামাজ, তিলাওয়াত, আদব (`docs/02` §4.10).
//
// আমল ও আদব rather than a literal "আচরণ": আচরণ is behaviour as a school report
// means it, and this register is about what a student *practises* — the prayer
// he kept, the sabaq he read, the manners he showed. A madrasah says আমল.
//
// The dictionaries share ONE FLAT NAMESPACE, so only the strings this module
// owns are here. `Student`, `Roll`, `Class`, `Section`, `Save`, `Discard`,
// `Saved`, `Grid view`, `Another class` and the question-type labels are
// already translated by attendance, students, common and forms — reusing them
// is the point of the shared namespace, and redefining one here would silently
// change it for those screens too.
const conduct: Record<string, string> = {
  // ── The section, its nav row and its tabs ──────────────────────────────
  'Conduct': 'আমল ও আদব',
  'Sheet': 'রিপোর্ট খাতা',
  'Choose an institution in the header to fill the conduct sheet.':
    'আমল-আদবের খাতা পূরণ করতে উপরে একটি প্রতিষ্ঠান বেছে নিন।',

  // ── The sheet ──────────────────────────────────────────────────────────
  'Could not load the conduct sheet.': 'আমল-আদবের খাতা লোড করা যায়নি।',
  'Could not save the conduct sheet.': 'আমল-আদবের খাতা সেভ করা যায়নি।',
  'No class': 'কোনো শ্রেণি নেই',
  'Automatic': 'স্বয়ংক্রিয়',
  'Filled': 'পূরণ হয়েছে',
  'Mark all yes': 'সবাইকে হ্যাঁ দিন',
  'Mark all no': 'সবাইকে না দিন',
  'Previous student': 'আগের শিক্ষার্থী',
  'Next student': 'পরের শিক্ষার্থী',
  'One student': 'একজন করে',
  'students changed': 'জন শিক্ষার্থীর তথ্য বদলেছে',
  'You have unsaved answers on this sheet. Leave them?':
    'এই খাতায় কিছু উত্তর সেভ হয়নি। বাদ দেবেন?',
  'You can read this sheet but not fill it.':
    'আপনি খাতা দেখতে পারবেন, পূরণ করতে পারবেন না।',
  'This report has no questions yet. Add them on Settings → Questions.':
    'এই রিপোর্টে এখনো কোনো প্রশ্ন নেই। সেটিংস → প্রশ্নাবলী থেকে যোগ করুন।',
  'Not enrolled in this class.': 'এই শ্রেণিতে ভর্তি নেই।',
  'That question is not on this sheet.': 'ওই প্রশ্নটি এই খাতায় নেই।',

  // ── The setup screen ───────────────────────────────────────────────────
  'New report': 'নতুন রিপোর্ট',
  'Could not load the reports.': 'রিপোর্টগুলো লোড করা যায়নি।',
  'Could not save this report.': 'রিপোর্টটি সেভ করা যায়নি।',
  'A report names a section of the question bank, how often it is filled, and which classes it is for.':
    'একটি রিপোর্ট বলে দেয় — প্রশ্নভান্ডারের কোন অংশ জিজ্ঞাসা হবে, কত ঘনঘন পূরণ হবে, আর কোন শ্রেণির জন্য।',
  'No reports yet. A new one takes a name and a question section.':
    'এখনো কোনো রিপোর্ট নেই। নতুন একটিতে নাম আর প্রশ্নের অংশ দিলেই হয়।',
  'How often': 'কত ঘনঘন',
  'Daily': 'প্রতিদিন',
  'Weekly': 'সাপ্তাহিক',
  'Per term': 'সাময়িক',
  'Question section': 'প্রশ্নের অংশ',
  'The slice of the question bank this sheet asks.':
    'প্রশ্নভান্ডারের যে অংশটি এই খাতায় জিজ্ঞাসা হবে।',
  'Every বিভাগ': 'সব বিভাগ',
  'Leave empty for every one of them.': 'সবগুলোর জন্য হলে খালি রাখুন।',
  'Questions on this sheet': 'এই খাতার প্রশ্ন',

  // ── Which questions one report asks ────────────────────────────────────
  // Two states, and the Bangla keeps them apart as plainly as the English:
  // একটি অংশের সবগুলো প্রশ্ন vs নিজের বেছে নেওয়া প্রশ্ন.
  'Asks every question in section': 'জিজ্ঞাসা করে এই অংশের সব প্রশ্ন —',
  'Asks its own chosen questions': 'জিজ্ঞাসা করে নিজের বেছে নেওয়া প্রশ্ন',
  'A question added to that section later joins this sheet on its own.':
    'ওই অংশে পরে নতুন প্রশ্ন যোগ করলে সেটি এই খাতায় আপনিই চলে আসবে।',
  'A question added to that section later does not join this sheet.':
    'ওই অংশে পরে নতুন প্রশ্ন যোগ করলে সেটি এই খাতায় আসবে না।',
  'Choose questions': 'প্রশ্ন বেছে নিন',
  'Change the questions': 'প্রশ্নগুলো বদলান',
  'Add a question…': 'একটি প্রশ্ন যোগ করুন…',
  'Every question is already on it.': 'সব প্রশ্নই এখানে আছে।',
  'Save the questions': 'প্রশ্নগুলো সেভ করুন',
  'Back to the whole section': 'আবার পুরো অংশে ফিরুন',
  'Could not save the questions.': 'প্রশ্নগুলো সেভ করা যায়নি।',
  'Save the report to choose which questions it asks.':
    'কোন প্রশ্নগুলো জিজ্ঞাসা হবে বাছতে রিপোর্টটি আগে সেভ করুন।',

  // ── Who is responsible ─────────────────────────────────────────────────
  // দায়িত্ব, not a lock: the wording says who is *meant* to fill it, and the
  // hint says outright that it stops nobody else.
  'Responsible': 'দায়িত্বে',
  'Responsible teachers': 'দায়িত্বপ্রাপ্ত শিক্ষক',
  'Who is meant to fill each report. It does not stop another teacher of that class filling it.':
    'কোন রিপোর্ট কার পূরণ করার কথা। ওই শ্রেণির অন্য শিক্ষক পূরণ করতে চাইলে বাধা নেই।',
  'Give the responsibility': 'দায়িত্ব দিন',
  'Nobody has been given a report yet.': 'এখনো কাউকে কোনো রিপোর্টের দায়িত্ব দেওয়া হয়নি।',
  'Leave it on the whole class unless one শাখা has its own teacher.':
    'কোনো শাখার আলাদা শিক্ষক না থাকলে পুরো শ্রেণিতেই রেখে দিন।',
  'Take this teacher off the report?': 'এই শিক্ষককে রিপোর্টের দায়িত্ব থেকে সরাবেন?',
  'Could not load who is responsible.': 'দায়িত্ব কার, তা লোড করা যায়নি।',
  'Could not save who is responsible.': 'দায়িত্ব সেভ করা যায়নি।',
  'Questions live in one bank, shared with the admission form. Add, reorder or retire them on Settings → Questions.':
    'প্রশ্নগুলো এক ভান্ডারেই থাকে — ভর্তি ফরমও সেখান থেকেই নেয়। যোগ করা, ক্রম বদলানো বা বাদ দেওয়া যায় সেটিংস → প্রশ্নাবলী থেকে।',
  'This section holds no questions yet.': 'এই অংশে এখনো কোনো প্রশ্ন নেই।',
  'Open Settings → Questions': 'সেটিংস → প্রশ্নাবলী খুলুন',

  // ── On the student's record ────────────────────────────────────────────
  'What was observed, newest first — নামাজ, তিলাওয়াত, আদব.':
    'যা যা লেখা হয়েছে, নতুনটি আগে — নামাজ, তিলাওয়াত, আদব।',
  'Nothing recorded yet.': 'এখনো কিছু লেখা হয়নি।',
};

export default conduct;
