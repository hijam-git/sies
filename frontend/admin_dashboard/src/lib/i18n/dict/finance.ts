/**
 * Accounts — the income and expense ledger, and the overview's money cards.
 *
 * Kept apart from `fees.ts` because the two modules are edited by different
 * people at different times, which is the whole reason the dictionary is split
 * per section (`dictionary.ts`).
 */
const finance: Record<string, string> = {
  // ── The module ────────────────────────────────────────────────────────
  Income: 'আয়',
  Expenses: 'ব্যয়',
  'What came in and what went out. Fee collections post themselves — everything else is entered here.':
    'কী এসেছে আর কী গেছে। ফি আদায় নিজে থেকেই যুক্ত হয় — বাকি সবকিছু এখানে লিখতে হয়।',

  // ── The list ──────────────────────────────────────────────────────────
  Entry: 'এন্ট্রি',
  Source: 'উৎস',
  Reference: 'রেফারেন্স',
  'Total income': 'মোট আয়',
  'Total expenses': 'মোট ব্যয়',
  'Entries listed': 'তালিকাভুক্ত এন্ট্রি',
  'Server total over the category and search filters. Reversed entries excluded.':
    'খাত ও খোঁজার ফিল্টার অনুযায়ী সার্ভারের হিসাব। বাতিল এন্ট্রি ধরা হয়নি।',
  'Narrowed by date on this screen — the total above covers every date.':
    'এই পাতায় তারিখ ধরে ছেঁকে দেখানো হচ্ছে — উপরের মোট হিসাবে সব তারিখ ধরা আছে।',
  'Voucher number, reference or description': 'ভাউচার নম্বর, রেফারেন্স বা বিবরণ',
  'Search the ledger': 'হিসাবে খুঁজুন',
  'Every category': 'সব খাত',
  Until: 'পর্যন্ত',
  'Nothing recorded here yet.': 'এখানে এখনো কিছু লেখা হয়নি।',
  'Could not load the ledger.': 'হিসাব আনা যায়নি।',

  // ── The read-only rule, which is the point of this screen ─────────────
  'From a receipt': 'রসিদ থেকে',
  'From payroll': 'বেতন থেকে',
  'Entered by hand': 'হাতে লেখা',
  'Correct this by reversing the receipt in Fees.':
    'সংশোধন করতে ফি পাতায় গিয়ে রসিদটি বাতিল করুন।',
  'Posted automatically — not editable here.':
    'স্বয়ংক্রিয়ভাবে যুক্ত — এখান থেকে সম্পাদনা করা যাবে না।',

  // ── Create and edit ───────────────────────────────────────────────────
  'Add income': 'আয় যোগ করুন',
  'Add expense': 'ব্যয় যোগ করুন',
  'Edit entry': 'এন্ট্রি সম্পাদনা',
  Category: 'খাত',
  'Cheque number, bill number, transaction id.': 'চেক নম্বর, বিল নম্বর, লেনদেন আইডি।',
  Attachment: 'সংযুক্তি',
  'A scan or a photo of the voucher. Uploaded after the entry is saved.':
    'ভাউচারের স্ক্যান বা ছবি। এন্ট্রি সংরক্ষণের পর আপলোড হয়।',
  'An attachment is already on this entry.': 'এই এন্ট্রিতে আগে থেকেই একটি সংযুক্তি আছে।',
  'The entry was saved, but the attachment did not upload.':
    'এন্ট্রিটি সংরক্ষিত হয়েছে, কিন্তু সংযুক্তিটি আপলোড হয়নি।',
  'The entry could not be saved.': 'এন্ট্রিটি সংরক্ষণ করা যায়নি।',

  // ── Categories ────────────────────────────────────────────────────────
  'Manage categories': 'খাত ব্যবস্থাপনা',
  'Income categories': 'আয়ের খাত',
  'Expense categories': 'ব্যয়ের খাত',
  'Add a category': 'নতুন খাত যোগ করুন',
  'Edit category': 'খাত সম্পাদনা',
  'Name in Bangla': 'বাংলা নাম',
  'No categories yet.': 'এখনো কোনো খাত নেই।',
  'The category could not be saved.': 'খাতটি সংরক্ষণ করা যায়নি।',
  'This is a seeded category. It can be switched off but not deleted — entries point at it.':
    'এটি একটি পূর্বনির্ধারিত খাত। নিষ্ক্রিয় করা যাবে, মুছে ফেলা যাবে না — এন্ট্রিগুলো এটির সঙ্গে যুক্ত।',

  // ── The overview's money cards ────────────────────────────────────────
  'Fee receipts, posted automatically to income': 'ফি রসিদ, স্বয়ংক্রিয়ভাবে আয়ে যুক্ত',
  'Owed across every unpaid, part-paid and overdue invoice':
    'সব বকেয়া, আংশিক পরিশোধিত ও মেয়াদোত্তীর্ণ বিলে পাওনা',
  'Expenses this month': 'এ মাসের ব্যয়',
  'Entered by hand in Accounts': 'হিসাব পাতায় হাতে লেখা',
  'Attendance and exam figures arrive with their modules.':
    'উপস্থিতি ও পরীক্ষার হিসাব সংশ্লিষ্ট মডিউলের সঙ্গে আসবে।',
  'Nothing is being hidden — the phases that take attendance and publish results have not been built yet, so those figures are honestly zero. The money figures above are live.':
    'কিছুই লুকানো হচ্ছে না — উপস্থিতি নেওয়া আর ফলাফল প্রকাশের ধাপগুলো এখনো তৈরি হয়নি, তাই ওই সংখ্যাগুলো সত্যিই শূন্য। উপরের টাকার হিসাবগুলো সরাসরি চলমান।',
};

export default finance;
