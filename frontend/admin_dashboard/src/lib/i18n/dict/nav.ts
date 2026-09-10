// Bangla for the sidebar, the top bar and the phase placeholder.
//
// The labels are an institution's own words, not a literal translation of the
// English: a madrasah says জামাত where a school says শ্রেণি, and both read
// ক্লাস without confusion, so the shared word wins.
const nav: Record<string, string> = {
  // Groups
  'Overview': 'ওভারভিউ',
  'Academics': 'শিক্ষা কার্যক্রম',
  'Students': 'শিক্ষার্থী',
  'Staff': 'কর্মী',
  'Attendance': 'হাজিরা',
  'Fees': 'ফি',
  'Accounts': 'হিসাব',
  'Exams': 'পরীক্ষা',
  'Reports': 'রিপোর্ট',
  'Notices': 'নোটিশ',
  'Settings': 'সেটিংস',
  'Users': 'ব্যবহারকারী',
  'Branches': 'প্রতিষ্ঠান',

  // Academics
  'Classes': 'ক্লাস',
  'Sections': 'শাখা',
  'Subjects': 'বিষয়',
  'Sessions': 'শিক্ষাবর্ষ',
  'Routine': 'রুটিন',

  // Students
  'All students': 'সব শিক্ষার্থী',
  'Admissions': 'ভর্তি',
  'Enrolment': 'শ্রেণিভুক্তি',
  'Documents': 'কাগজপত্র',

  // Staff
  'Teachers': 'শিক্ষক',
  'Employees': 'কর্মচারী',
  'Assignments': 'দায়িত্ব বণ্টন',

  // Attendance
  'Month register': 'মাসিক হাজিরা খাতা',
  'Class attendance': 'ক্লাসের হাজিরা',
  'Daily register': 'দৈনিক হাজিরা',
  'Attendance reports': 'হাজিরার রিপোর্ট',

  // Fees
  'Fee structure': 'ফি কাঠামো',
  'Invoices': 'বিল',
  'Collect fee': 'ফি আদায়',
  'Dues': 'বকেয়া',
  'Discounts': 'ছাড়',

  // Accounts
  'Income': 'আয়',
  'Expenses': 'ব্যয়',
  'Salary': 'বেতন',
  'Ledger': 'খতিয়ান',

  // Exams
  'Exam list': 'পরীক্ষার তালিকা',
  'Schedule': 'সময়সূচি',
  'Marks entry': 'নম্বর এন্ট্রি',
  'Results': 'ফলাফল',
  'Marksheets': 'মার্কশিট',

  // Reports
  'Student reports': 'শিক্ষার্থী রিপোর্ট',
  'Fee reports': 'ফি রিপোর্ট',
  'Finance reports': 'আর্থিক রিপোর্ট',
  'Exam reports': 'পরীক্ষার রিপোর্ট',
  'Branch comparison': 'প্রতিষ্ঠানের তুলনা',

  // Notices
  'Notice board': 'নোটিশ বোর্ড',
  'SMS': 'এসএমএস',

  // Settings
  'Institution': 'প্রতিষ্ঠানের তথ্য',
  'Fee categories': 'ফি খাত',
  'Grade scale': 'গ্রেড স্কেল',
  'Form templates': 'ফরম টেমপ্লেট',

  // Users
  'Accounts & logins': 'অ্যাকাউন্ট ও লগইন',
  'Roles & permissions': 'রোল ও অনুমতি',
  'Live activity': 'সরাসরি কার্যক্রম',

  // Branches
  'All institutions': 'সব প্রতিষ্ঠান',
  'Add institution': 'প্রতিষ্ঠান যোগ করুন',

  // Top bar
  'Toggle menu': 'মেনু দেখান/লুকান',
  'Logout': 'লগআউট',
  'Signed in as': 'লগইন করেছেন',
  'All institutions (platform view)': 'সব প্রতিষ্ঠান (প্ল্যাটফর্ম ভিউ)',
  'Viewing institution': 'যে প্রতিষ্ঠান দেখছেন',
  'Switch institution': 'প্রতিষ্ঠান বদলান',

  // The honest placeholder behind a nav item whose module is a later phase.
  'Coming soon': 'শীঘ্রই আসছে',
  'This screen is built in phase PHASE.': 'এই স্ক্রিনটি ফেজ PHASE-এ তৈরি হবে।',
  'The navigation is complete so the shape of the system is visible from the start. Nothing here is hidden from you — this module simply has not been built yet.':
    'শুরু থেকেই যেন পুরো সিস্টেমের গঠন বোঝা যায়, সে জন্য মেনু সম্পূর্ণ রাখা হয়েছে। আপনার কাছ থেকে কিছু লুকানো হয়নি — এই অংশটি কেবল এখনো তৈরি হয়নি।',
  'Back to overview': 'ওভারভিউতে ফিরুন',
};
export default nav;
