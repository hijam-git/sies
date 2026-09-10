/**
 * Fees — the counter, the invoices, the dues and the fee heads.
 *
 * Keys are the English source strings exactly as they appear in `t('…')`, so a
 * typo in a component reads as "the Bangla did not apply" rather than as an
 * error.
 *
 * The vocabulary follows what a Bangladeshi institution's office actually says,
 * not a literal rendering: a receipt is রসিদ, an invoice বিল, a fee head ফি খাত,
 * a waiver মওকুফ, a reversal বাতিল. Those are the words on the paper the screens
 * replace.
 */
const fees: Record<string, string> = {
  // ── The module ────────────────────────────────────────────────────────
  'Collect fee': 'ফি আদায়',
  Invoices: 'বিলসমূহ',
  Dues: 'বকেয়া',
  'Fee setup': 'ফি খাত',
  'Take money at the counter, and see what is still owed.':
    'কাউন্টারে টাকা নিন, আর কার কত বকেয়া আছে দেখুন।',
  'You may look at fees but not collect them.':
    'আপনি ফি দেখতে পারবেন, কিন্তু আদায় করতে পারবেন না।',

  // ── Invoice states — `docs/06` #8 ─────────────────────────────────────
  Unpaid: 'বকেয়া',
  'Partly paid': 'আংশিক পরিশোধিত',
  Paid: 'পরিশোধিত',
  Overdue: 'মেয়াদোত্তীর্ণ',
  Waived: 'মওকুফ',

  // ── The eight ways money arrives ──────────────────────────────────────
  Cash: 'নগদ টাকা',
  bKash: 'বিকাশ',
  Nagad: 'নগদ',
  Rocket: 'রকেট',
  Bank: 'ব্যাংক',
  Cheque: 'চেক',
  Card: 'কার্ড',
  Online: 'অনলাইন',

  // ── How often a head is charged ───────────────────────────────────────
  'One time': 'এককালীন',
  'Per session': 'শিক্ষাবর্ষভিত্তিক',
  'Per exam': 'পরীক্ষাভিত্তিক',
  Custom: 'প্রযোজ্য ক্ষেত্রে',

  // ── Collect fee ───────────────────────────────────────────────────────
  'Find the student': 'শিক্ষার্থী খুঁজুন',
  'Search by name, mobile number or admission number.':
    'নাম, মোবাইল নম্বর বা ভর্তি নম্বর দিয়ে খুঁজুন।',
  'Name, mobile or admission number': 'নাম, মোবাইল বা ভর্তি নম্বর',
  'Search students': 'শিক্ষার্থী খুঁজুন',
  'Searching…': 'খোঁজা হচ্ছে…',
  'No student matched that. Try part of the name, or the full mobile number.':
    'এই তথ্যে কোনো শিক্ষার্থী পাওয়া যায়নি। নামের অংশ, বা পুরো মোবাইল নম্বর দিয়ে দেখুন।',
  Change: 'পরিবর্তন',
  'Outstanding invoices': 'বকেয়া বিলসমূহ',
  'Nothing is outstanding for this student.': 'এই শিক্ষার্থীর কোনো বকেয়া নেই।',
  'Could not load this student’s invoices.': 'এই শিক্ষার্থীর বিল আনা যায়নি।',
  'Take the payment': 'টাকা গ্রহণ করুন',
  'Amount received': 'গৃহীত পরিমাণ',
  'Part payment is fine — enter what is being handed over.':
    'আংশিক পরিশোধ স্বাভাবিক — যত টাকা দেওয়া হচ্ছে তা লিখুন।',
  'Full balance': 'সম্পূর্ণ বকেয়া',
  'Balance remaining after this payment': 'এই পরিশোধের পর অবশিষ্ট বকেয়া',
  'This clears the invoice in full.': 'এতে বিলটি সম্পূর্ণ পরিশোধ হয়ে যাবে।',
  'This is a part payment — the invoice stays open.':
    'এটি আংশিক পরিশোধ — বিলটি খোলা থাকবে।',
  Method: 'মাধ্যম',
  'Transaction id': 'লেনদেন আইডি',
  'A mobile payment needs its transaction id to be reconciled later.':
    'মোবাইল পেমেন্ট পরে মিলিয়ে দেখতে লেনদেন আইডি লাগবে।',
  'Cheque number, bank slip or card reference. Optional for cash.':
    'চেক নম্বর, ব্যাংক স্লিপ বা কার্ড রেফারেন্স। নগদের ক্ষেত্রে প্রয়োজন নেই।',
  'e.g. 8N7A2K1B9C': 'যেমন 8N7A2K1B9C',
  'Date received': 'গ্রহণের তারিখ',
  Note: 'মন্তব্য',
  'Optional — anything the receipt should say': 'ঐচ্ছিক — রসিদে যা লেখা থাকবে',
  'This collection posts itself to Income automatically — do not enter it again in Accounts.':
    'এই আদায় স্বয়ংক্রিয়ভাবে আয় খাতে যুক্ত হয়ে যায় — হিসাব পাতায় আবার লিখবেন না।',
  'Confirm and print receipt': 'নিশ্চিত করে রসিদ ছাপুন',
  'Taking payment…': 'টাকা নেওয়া হচ্ছে…',
  Remaining: 'অবশিষ্ট',
  'The payment was not taken. Nothing has changed.':
    'টাকা গ্রহণ করা হয়নি। কিছুই পরিবর্তন হয়নি।',

  // ── The receipt ───────────────────────────────────────────────────────
  'Payment received': 'টাকা গৃহীত হয়েছে',
  Received: 'গৃহীত',
  Receipt: 'রসিদ',
  Receipts: 'রসিদসমূহ',
  'Print A4': 'A4 কাগজে ছাপুন',
  'Print on the roll (80mm)': 'রোল প্রিন্টারে ছাপুন (৮০ মিমি)',
  'Collected by': 'আদায়কারী',
  'Invoice total': 'বিলের মোট',
  'Paid to date': 'এ পর্যন্ত পরিশোধিত',
  'Balance remaining': 'অবশিষ্ট বকেয়া',
  'The print window was blocked. Allow pop-ups for this site and try again.':
    'প্রিন্ট উইন্ডো আটকে গেছে। এই সাইটের জন্য পপ-আপ চালু করে আবার চেষ্টা করুন।',

  // ── Invoices ──────────────────────────────────────────────────────────
  Invoice: 'বিল',
  'Fee head': 'ফি খাত',
  'Fee month': 'ফি-এর মাস',
  'Month, e.g. 2026-03': 'মাস, যেমন 2026-03',
  'Every fee head': 'সব ফি খাত',
  'Every session': 'সব শিক্ষাবর্ষ',
  'Due date': 'শেষ তারিখ',
  Due: 'শেষ তারিখ',
  'Due from': 'তারিখ থেকে',
  'Due until': 'তারিখ পর্যন্ত',
  Balance: 'বকেয়া',
  Payable: 'প্রদেয়',
  Amount: 'পরিমাণ',
  Discount: 'ছাড়',
  Fine: 'জরিমানা',
  'Invoice number, student name or id': 'বিল নম্বর, শিক্ষার্থীর নাম বা আইডি',
  'Search invoices': 'বিল খুঁজুন',
  'No invoice matches these filters.': 'এই ফিল্টারে কোনো বিল নেই।',
  'Could not load the invoices.': 'বিলসমূহ আনা যায়নি।',
  'Nothing has been collected against this invoice.':
    'এই বিলের বিপরীতে এখনো কিছু আদায় হয়নি।',
  Reversed: 'বাতিল',
  Reverse: 'বাতিল করুন',
  Reason: 'কারণ',
  'Reverse this receipt': 'এই রসিদ বাতিল করুন',
  'Waive this balance': 'এই বকেয়া মওকুফ করুন',
  'Waive the remaining balance': 'অবশিষ্ট বকেয়া মওকুফ করুন',
  'Waiving writes the balance off. The invoice stays on the record, marked waived, with this reason attached.':
    'মওকুফ করলে বকেয়া বাদ দেওয়া হয়। বিলটি রেকর্ডে থেকে যায়, মওকুফ হিসেবে চিহ্নিত হয়, এবং এই কারণটি সঙ্গে থাকে।',
  'A receipt is never deleted — deleting one would destroy an accounting record. It is marked reversed, its income entry is reversed with it, and the balance goes back up.':
    'রসিদ কখনো মুছে ফেলা হয় না — মুছলে হিসাবের রেকর্ড নষ্ট হয়। রসিদটি বাতিল হিসেবে চিহ্নিত হয়, সঙ্গে আয়ের এন্ট্রিও বাতিল হয়, আর বকেয়া আবার বেড়ে যায়।',
  'Why is this being done? Six months from now this is the only explanation there is.':
    'কেন এটি করা হচ্ছে? ছয় মাস পর এটিই একমাত্র ব্যাখ্যা হয়ে থাকবে।',
  'That could not be done.': 'কাজটি করা যায়নি।',

  // ── Dues ──────────────────────────────────────────────────────────────
  'By student': 'শিক্ষার্থীভিত্তিক',
  'By class': 'শ্রেণিভিত্তিক',
  Refresh: 'নতুন করে দেখুন',
  'Total outstanding': 'মোট বকেয়া',
  'Across every unpaid, part-paid and overdue invoice':
    'সব বকেয়া, আংশিক পরিশোধিত ও মেয়াদোত্তীর্ণ বিল মিলিয়ে',
  'Invoices owing': 'বকেয়া বিলের সংখ্যা',
  'Counted by the server, not by this screen': 'সার্ভারের গণনা, এই পাতার নয়',
  'Past the due date': 'মেয়াদোত্তীর্ণ',
  'Nothing overdue': 'কোনো মেয়াদোত্তীর্ণ বিল নেই',
  'How long it has been owed': 'কত দিন ধরে বকেয়া',
  'Not yet due': 'সময় এখনো হয়নি',
  '0–30 days': '০–৩০ দিন',
  '31–60 days': '৩১–৬০ দিন',
  '61–90 days': '৬১–৯০ দিন',
  'Over 90 days': '৯০ দিনের বেশি',
  Oldest: 'সবচেয়ে পুরনো',
  Outstanding: 'বকেয়া',
  days: 'দিন',
  invoices: 'বিল',
  'No class recorded': 'শ্রেণি লেখা নেই',
  'Nothing is outstanding.': 'কোনো বকেয়া নেই।',
  'Could not load the dues.': 'বকেয়ার তথ্য আনা যায়নি।',
  'There are more outstanding invoices than this screen reads at once. The totals in the cards above are the server’s and remain correct; narrow by session to see every row.':
    'এই পাতা একবারে যত বিল পড়তে পারে, বকেয়া বিল তার চেয়ে বেশি। উপরের কার্ডের হিসাব সার্ভারের, সেগুলো সঠিক আছে; প্রতিটি সারি দেখতে শিক্ষাবর্ষ ধরে ছেঁকে নিন।',

  // ── Fee setup ─────────────────────────────────────────────────────────
  'Default amount': 'নির্ধারিত পরিমাণ',
  'No amount set': 'পরিমাণ দেওয়া নেই',
  Charged: 'আদায়ের ধরন',
  'Applies to': 'প্রযোজ্য',
  'Every student': 'সব শিক্ষার্থী',
  'Residential students only': 'শুধু আবাসিক শিক্ষার্থী',
  'Transport users only': 'শুধু পরিবহন ব্যবহারকারী',
  'Only residential students': 'শুধু আবাসিক শিক্ষার্থী',
  'Only students using transport': 'শুধু পরিবহন ব্যবহারকারী শিক্ষার্থী',
  'No stream ticked means every stream.': 'কোনো বিভাগ নির্বাচন না করলে সব বিভাগে প্রযোজ্য।',
  Mandatory: 'আবশ্যিক',
  Refundable: 'ফেরতযোগ্য',
  Seeded: 'পূর্বনির্ধারিত',
  Off: 'নিষ্ক্রিয়',
  'active fee heads have no default amount.': 'টি সক্রিয় ফি খাতে নির্ধারিত পরিমাণ নেই।',
  'An invoice cannot be raised for a head with no amount — the monthly job skips it silently, so nothing else on any screen would ever tell you.':
    'পরিমাণ না থাকলে সেই খাতে বিল তৈরি হয় না — মাসিক কাজটি নীরবে সেটি বাদ দিয়ে যায়, আর অন্য কোনো পাতায় এর কোনো ইঙ্গিতও থাকে না।',
  'The default amount cannot be edited from here yet.':
    'নির্ধারিত পরিমাণ এখান থেকে এখনো সম্পাদনা করা যায় না।',
  'This build of the API does not send or accept the field on a fee head. Set it in Django admin until it does; this screen will edit it as soon as the field is served.':
    'বর্তমান API ফি খাতের এই ঘরটি পাঠায় না এবং গ্রহণও করে না। ততদিন Django admin থেকে ঠিক করুন; API পাঠানো শুরু করলেই এই পাতা থেকে সম্পাদনা করা যাবে।',
  'Read-only: this build of the API does not accept the field.':
    'শুধু পড়ার জন্য: বর্তমান API এই ঘরটি গ্রহণ করে না।',
  'Leave empty only if the amount differs per student every time.':
    'প্রতিবার প্রতিটি শিক্ষার্থীর জন্য পরিমাণ আলাদা হলেই কেবল খালি রাখুন।',
  'This is a seeded head. It can be switched off but not deleted — invoices point at it.':
    'এটি একটি পূর্বনির্ধারিত খাত। নিষ্ক্রিয় করা যাবে, মুছে ফেলা যাবে না — বিলগুলো এটির সঙ্গে যুক্ত।',
  'No fee heads yet. They are seeded when the institution is created.':
    'এখনো কোনো ফি খাত নেই। প্রতিষ্ঠান তৈরির সময় এগুলো যুক্ত হয়।',
  'The fee head could not be saved.': 'ফি খাতটি সংরক্ষণ করা যায়নি।',
};

export default fees;
