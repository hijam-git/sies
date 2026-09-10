// Bangla for the sidebar, the top bar and the phase placeholder.
//
// The labels are an institution's own words, not a literal translation: a
// madrasah says জামাত where a school says শ্রেণি, and both read ক্লাস without
// confusion, so the shared word wins.
//
// Thirteen entries, matching `pages/navigation.ts`. The in-page tab labels live
// in `dict/admin.ts` with the screens that draw them.
const nav: Record<string, string> = {
  'Overview': 'ওভারভিউ',
  // A teacher's own weekly timetable — রুটিন is the word every institution here
  // uses for one; সময়সূচি reads as a bus schedule.
  'My routine': 'আমার রুটিন',
  'Students': 'শিক্ষার্থী',
  'Staff': 'কর্মী',
  'Academics': 'শিক্ষা কার্যক্রম',
  'Attendance': 'হাজিরা',
  'Fees': 'ফি',
  'Accounts': 'হিসাব',
  'Exams': 'পরীক্ষা',
  'Reports': 'রিপোর্ট',
  'Settings': 'সেটিংস',
  'Users': 'ব্যবহারকারী',

  // Tabs inside Settings and Users that are still placeholders — the tab strip
  // is drawn from these labels even where the panel is not built yet.
  'Fee categories': 'ফি খাত',
  'Form templates': 'ফরম টেমপ্লেট',
  'Live activity': 'সরাসরি কার্যক্রম',

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
