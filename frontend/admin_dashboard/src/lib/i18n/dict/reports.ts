// Bangla for the Reports screen (`docs/02` §4.8).
//
// Report headings are the words an office uses on the sheet it files, not
// literal translations: হাজিরা for attendance, আদায় for collection, বকেয়া for
// what is still owed, মেধা তালিকা for a merit list. An accountant reading this
// screen is checking it against a paper register that uses these words.
const reports: Record<string, string> = {
  'Could not load this report.': 'এই রিপোর্টটি আনা যায়নি।',
  'Report': 'রিপোর্ট',
  'Group': 'গ্রুপ',
  'Grouped by': 'যেভাবে ভাগ করা',
  'Kind': 'ধরন',
  'Line': 'খাত',
  'Entries': 'এন্ট্রি',
  'Amount': 'টাকা',

  // ── Students ───────────────────────────────────────────────────────────
  'Strength by class': 'শ্রেণিভিত্তিক শিক্ষার্থী সংখ্যা',
  'Admissions over a period': 'সময়ভিত্তিক ভর্তি',
  'Withdrawals': 'ছাড়পত্র',
  'On the roll': 'তালিকাভুক্ত',
  'Strength': 'সংখ্যা',
  'Boys': 'ছাত্র',
  'Girls': 'ছাত্রী',
  'Month': 'মাস',
  'Applied': 'আবেদন',
  'Admitted': 'ভর্তি হয়েছে',
  'Rejected': 'বাতিল',
  'Pending': 'অপেক্ষমাণ',
  'Left on': 'ছেড়েছে',
  'Applications': 'আবেদনসমূহ',
  'Nobody is enrolled in this session yet.': 'এই শিক্ষাবর্ষে এখনো কেউ ভর্তি হয়নি।',
  'No applications in this period.': 'এই সময়ে কোনো আবেদন নেই।',
  'Nobody withdrew in this period.': 'এই সময়ে কেউ ছাড়পত্র নেয়নি।',

  // ── Attendance ─────────────────────────────────────────────────────────
  'Monthly percentage by class': 'শ্রেণিভিত্তিক মাসিক হাজিরার হার',
  'Defaulter list': 'অনিয়মিতদের তালিকা',
  'Days marked': 'হাজিরা নেওয়া দিন',
  'Attendance is kept by month, so this report reads': 'হাজিরা মাসভিত্তিক, তাই এই রিপোর্ট দেখাচ্ছে',
  'Below': 'নিচে',
  'Present': 'উপস্থিত',
  'Absent': 'অনুপস্থিত',
  'No attendance has been taken for this month.': 'এই মাসে কোনো হাজিরা নেওয়া হয়নি।',
  'Nobody is below the line this month.': 'এই মাসে কেউ নির্ধারিত হারের নিচে নেই।',

  // ── Fees ───────────────────────────────────────────────────────────────
  'Collection': 'আদায়',
  'Collected': 'আদায়কৃত',
  'Receipts': 'রসিদ',
  'Outstanding dues': 'বকেয়া',
  'Outstanding': 'বকেয়া',
  'Invoices': 'বিল',
  'invoices': 'টি বিল',
  'Payable': 'প্রদেয়',
  'Paid': 'পরিশোধিত',
  'By day': 'দিন অনুযায়ী',
  'By month': 'মাস অনুযায়ী',
  'By category': 'খাত অনুযায়ী',
  'Oldest due': 'সবচেয়ে পুরনো তারিখ',
  'Invoices whose due date has passed and which are not paid in full.':
    'যেসব বিলের তারিখ পেরিয়ে গেছে অথচ পুরোপুরি পরিশোধ হয়নি।',
  'Nothing was collected in this period.': 'এই সময়ে কোনো আদায় হয়নি।',
  'Nothing is outstanding.': 'কোনো বকেয়া নেই।',
  'Nobody is overdue.': 'কারো বিল বকেয়া নেই।',

  // ── Finance ────────────────────────────────────────────────────────────
  'Income and expense': 'আয়-ব্যয়',
  'Category breakdown': 'খাতভিত্তিক হিসাব',
  'Compare institutions': 'প্রতিষ্ঠান তুলনা',
  'Income': 'আয়',
  'Expense': 'ব্যয়',
  'Net': 'নিট',
  'Institution': 'প্রতিষ্ঠান',
  'Nothing was posted in this period.': 'এই সময়ে কোনো এন্ট্রি নেই।',
  'No institutions to compare.': 'তুলনা করার মতো কোনো প্রতিষ্ঠান নেই।',
  'Every institution on the platform, side by side. Collection is paid against payable for the session; the money is all-time until the ledger gains a date range.':
    'প্ল্যাটফর্মের সব প্রতিষ্ঠান পাশাপাশি। আদায়ের হার শিক্ষাবর্ষের প্রদেয়ের বিপরীতে; খতিয়ানে তারিখের সীমা যুক্ত না হওয়া পর্যন্ত টাকার অঙ্ক সর্বমোট।',
  'Attendance is not compared here: the only endpoint that reads attendance is one class’s month register, so a platform-wide figure would be one request per class per institution. It needs a summary endpoint.':
    'এখানে হাজিরা তুলনা করা হয়নি: হাজিরা পড়ার একমাত্র উপায় এক শ্রেণির এক মাসের রেজিস্টার, তাই প্ল্যাটফর্মজুড়ে হিসাব করতে প্রতিটি শ্রেণির জন্য আলাদা অনুরোধ লাগত। এর জন্য একটি সারাংশ এন্ডপয়েন্ট দরকার।',

  // ── Exams ──────────────────────────────────────────────────────────────
  'Tabulation': 'ট্যাবুলেশন',
  'Merit list': 'মেধা তালিকা',
  'Subject analysis': 'বিষয়ভিত্তিক বিশ্লেষণ',
  'Choose an exam and a class.': 'একটি পরীক্ষা ও শ্রেণি বেছে নিন।',
  'Choose an exam': 'পরীক্ষা বেছে নিন',
  'Passed': 'উত্তীর্ণ',
  'Pass rate': 'উত্তীর্ণের হার',
  'Published': 'প্রকাশিত',
  'Not published': 'অপ্রকাশিত',
  'Percentage': 'শতকরা',
  'Grade': 'গ্রেড',
  'Rank': 'মেধাক্রম',
  'Marks entered': 'নম্বর দেওয়া হয়েছে',
  'Average': 'গড়',
  'Highest': 'সর্বোচ্চ',
  'No marks have been entered for this class.': 'এই শ্রেণির কোনো নম্বর দেওয়া হয়নি।',
  'Nobody has passed this exam yet.': 'এই পরীক্ষায় এখনো কেউ উত্তীর্ণ হয়নি।',
  'classes could not be read, and are not in these figures.':
      'শ্রেণির হাজিরা আনা যায়নি, তাই এই হিসাবে নেই।',
  'without marks': 'নম্বর দেওয়া হয়নি',
  'Choose an institution in the header to read its registers.':
    'রেজিস্টার দেখতে উপরের তালিকা থেকে একটি প্রতিষ্ঠান বাছুন।',
  'This report reads at most 2,000 rows per list, and one of them reached that. The figures below are understated — narrow the period or the session.':
    'এই রিপোর্ট প্রতিটি তালিকা থেকে সর্বোচ্চ ২,০০০ সারি পড়ে, এবং একটি তালিকা সেই সীমায় পৌঁছেছে। নিচের হিসাব কম দেখাচ্ছে — সময়কাল বা শিক্ষাবর্ষ ছোট করুন।',
};

export default reports;
