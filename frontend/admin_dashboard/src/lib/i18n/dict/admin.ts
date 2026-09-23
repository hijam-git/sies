// Bangla for the phase 1 admin screens: institutions, settings, streams and
// sessions, accounts, roles and the activity feed.
//
// The words are an institution's own, not a literal translation: an admin says
// প্রতিষ্ঠান for a branch and শিক্ষাবর্ষ for a session, and a translation that
// says শাখা for both is a screen nobody can read quickly.
const admin: Record<string, string> = {
  // ── Institutions ────────────────────────────────────────────────────────
  'Institutions': 'প্রতিষ্ঠান',
  'Add institution': 'প্রতিষ্ঠান যোগ করুন',
  'Edit institution': 'প্রতিষ্ঠান সম্পাদনা',
  'Institution created': 'প্রতিষ্ঠান তৈরি হয়েছে',
  'Institution': 'প্রতিষ্ঠান',
  'Institution type': 'প্রতিষ্ঠানের ধরন',
  'Madrasah': 'মাদ্রাসা',
  'School': 'স্কুল',
  'College': 'কলেজ',
  'Combined': 'সমন্বিত',
  'All types': 'সব ধরন',
  'Code': 'কোড',
  'Established year': 'প্রতিষ্ঠার সাল',
  'District': 'জেলা',
  'Thana / Upazila': 'থানা / উপজেলা',
  'Email': 'ইমেইল',
  'Name (English)': 'নাম (ইংরেজি)',
  'Name (Bangla)': 'নাম (বাংলা)',
  'Name (Arabic)': 'নাম (আরবি)',
  'Shown on certificates and the printed form': 'সনদ ও ছাপা ফরমে দেখা যাবে',
  'Selects which streams and defaults get seeded':
    'কোন বিভাগ ও ডিফল্টগুলো তৈরি হবে তা এটি ঠিক করে',
  'Short and unique — it prefixes every admission and receipt number':
    'সংক্ষিপ্ত ও অনন্য — প্রতিটি ভর্তি ও রসিদ নম্বরের শুরুতে এটি বসে',
  'Search by name, code or district': 'নাম, কোড বা জেলা দিয়ে খুঁজুন',
  'No institutions yet.': 'এখনো কোনো প্রতিষ্ঠান নেই।',
  'Could not load the institutions.': 'প্রতিষ্ঠানের তালিকা আনা যায়নি।',
  'Could not save this institution.': 'এই প্রতিষ্ঠানটি সেভ করা যায়নি।',
  'Could not load this institution.': 'এই প্রতিষ্ঠানের তথ্য আনা যায়নি।',
  'Only a platform administrator can see the list of institutions.':
    'শুধুমাত্র প্ল্যাটফর্ম অ্যাডমিন প্রতিষ্ঠানের তালিকা দেখতে পারেন।',
  'Streams seeded from the institution type': 'প্রতিষ্ঠানের ধরন অনুযায়ী তৈরি বিভাগসমূহ',
  'No streams were seeded. Add them under Settings.':
    'কোনো বিভাগ তৈরি হয়নি। সেটিংস থেকে যোগ করুন।',
  'Rename these to the institution’s own words under Settings, then open its first academic year.':
    'সেটিংস থেকে এগুলোর নাম প্রতিষ্ঠানের নিজস্ব ভাষায় বদলে নিন, তারপর প্রথম শিক্ষাবর্ষ খুলুন।',
  'Done': 'সম্পন্ন',

  // ── Institution policy ──────────────────────────────────────────────────
  'Attendance, fines and activity': 'হাজিরা, জরিমানা ও কার্যক্রম',
  'Teachers may only reach their assigned classes':
    'শিক্ষকরা কেবল তাঁদের নির্ধারিত ক্লাসে ঢুকতে পারবেন',
  'A small institution where everyone covers everything can switch this off.':
    'ছোট প্রতিষ্ঠানে যেখানে সবাই সব কাজ করেন, সেখানে এটি বন্ধ রাখা যায়।',
  'Attendance window (minutes)': 'হাজিরার সময়সীমা (মিনিট)',
  'How long after a period starts a teacher may still mark it':
    'ক্লাস শুরুর কত মিনিট পর পর্যন্ত শিক্ষক হাজিরা দিতে পারবেন',
  'Keep activity for (days)': 'কার্যক্রম রাখা হবে (দিন)',
  'Older entries are pruned nightly': 'পুরোনো এন্ট্রি প্রতি রাতে মুছে ফেলা হয়',
  'Weekly off days': 'সাপ্তাহিক ছুটি',
  'Saturday': 'শনিবার',
  'Sunday': 'রবিবার',
  'Monday': 'সোমবার',
  'Tuesday': 'মঙ্গলবার',
  'Wednesday': 'বুধবার',
  'Thursday': 'বৃহস্পতিবার',
  'Friday': 'শুক্রবার',
  'Late fee rule': 'বিলম্ব ফি নিয়ম',
  'Per day': 'প্রতিদিন',
  'Grace days': 'ছাড়ের দিন',
  'Maximum fine': 'সর্বোচ্চ জরিমানা',
  'This institution is open': 'এই প্রতিষ্ঠানটি চালু আছে',

  // ── Settings ────────────────────────────────────────────────────────────
  'Streams & Sessions': 'বিভাগ ও শিক্ষাবর্ষ',
  'Choose an institution in the header to edit its settings.':
    'সেটিংস বদলাতে উপরের তালিকা থেকে একটি প্রতিষ্ঠান বাছুন।',
  'Choose an institution in the header to edit its streams and sessions.':
    'বিভাগ ও শিক্ষাবর্ষ বদলাতে উপরের তালিকা থেকে একটি প্রতিষ্ঠান বাছুন।',
  'You can see these settings but not change them.':
    'আপনি এই সেটিংস দেখতে পারেন, বদলাতে পারেন না।',

  // ── Streams and sessions ────────────────────────────────────────────────
  'Streams': 'বিভাগ',
  'Sessions': 'শিক্ষাবর্ষ',
  'Add stream': 'বিভাগ যোগ করুন',
  'Edit stream': 'বিভাগ সম্পাদনা',
  'Add session': 'শিক্ষাবর্ষ যোগ করুন',
  'Edit session': 'শিক্ষাবর্ষ সম্পাদনা',
  'Order': 'ক্রম',
  'Current': 'চলমান',
  'Make current': 'চলমান করুন',
  'Lower case, unique here. Other records point at it.':
    'ছোট হাতের অক্ষরে, এখানে অনন্য। অন্য তথ্য এটির দিকে নির্দেশ করে।',
  'Your institution’s own spelling': 'আপনাদের প্রতিষ্ঠানের নিজস্ব বানান',
  'For example 2026 or 2026–27': 'যেমন ২০২৬ বা ২০২৬–২৭',
  'No streams yet.': 'এখনো কোনো বিভাগ নেই।',
  'No sessions yet.': 'এখনো কোনো শিক্ষাবর্ষ নেই।',
  'This is now the current session.': 'এটিই এখন চলমান শিক্ষাবর্ষ।',
  'This is the current session.': 'এটিই চলমান শিক্ষাবর্ষ।',
  'Could not load streams and sessions.': 'বিভাগ ও শিক্ষাবর্ষ আনা যায়নি।',
  'Could not save this stream.': 'এই বিভাগটি সেভ করা যায়নি।',
  'Could not save this session.': 'এই শিক্ষাবর্ষটি সেভ করা যায়নি।',
  'Could not change the current session.': 'চলমান শিক্ষাবর্ষ বদলানো যায়নি।',

  // ── Accounts ────────────────────────────────────────────────────────────
  'Accounts': 'অ্যাকাউন্ট',
  'Roles': 'রোল',
  'Add account': 'অ্যাকাউন্ট যোগ করুন',
  'Edit account': 'অ্যাকাউন্ট সম্পাদনা',
  'Search by name or phone': 'নাম বা ফোন দিয়ে খুঁজুন',
  'User type': 'ব্যবহারকারীর ধরন',
  'Platform admin': 'প্ল্যাটফর্ম অ্যাডমিন',
  'Platform accountant': 'প্ল্যাটফর্ম হিসাবরক্ষক',
  'Principal': 'অধ্যক্ষ / মুহতামিম',
  'Accountant': 'হিসাবরক্ষক',
  'Teacher': 'শিক্ষক',
  'Employee': 'কর্মচারী',
  'Student': 'শিক্ষার্থী',
  'Role': 'রোল',
  'No role': 'কোনো রোল নেই',
  'All roles': 'সব রোল',
  'Language': 'ভাষা',
  'Password': 'পাসওয়ার্ড',
  'New password': 'নতুন পাসওয়ার্ড',
  'Leave blank to set it later, in person.':
    'পরে সামনাসামনি দিতে চাইলে খালি রাখুন।',
  '11 digits. This is the login.': '১১ সংখ্যা। এটিই লগইন।',
  'Which institution this account belongs to': 'এই অ্যাকাউন্টটি কোন প্রতিষ্ঠানের',
  'Choose one': 'একটি বাছুন',
  'A starting point for their permissions, not a cage':
    'অনুমতির শুরুর বিন্দু, বাঁধন নয়',
  'Make them change this password at first sign-in':
    'প্রথম লগইনে পাসওয়ার্ড বদলাতে বাধ্য করুন',
  'A password said out loud in order to hand it over must not stay the password.':
    'যে পাসওয়ার্ড মুখে বলে হস্তান্তর করা হয়েছে, সেটি পাসওয়ার্ড থেকে যাওয়া উচিত নয়।',
  'Last login': 'শেষ লগইন',
  'Deactivate': 'নিষ্ক্রিয় করুন',
  'Reactivate': 'আবার চালু করুন',
  'No accounts yet.': 'এখনো কোনো অ্যাকাউন্ট নেই।',
  'Could not load the accounts.': 'অ্যাকাউন্টের তালিকা আনা যায়নি।',
  'Could not save this account.': 'এই অ্যাকাউন্টটি সেভ করা যায়নি।',
  'Could not change this account.': 'এই অ্যাকাউন্টটি বদলানো যায়নি।',

  // ── Permissions ─────────────────────────────────────────────────────────
  'Permissions': 'অনুমতি',
  'Customised': 'নিজস্বভাবে সাজানো',
  'Follows the preset': 'রোলের ছক অনুসরণ করে',
  'Start from a preset': 'একটি ছক থেকে শুরু করুন',
  'Back to the preset': 'রোলের ছকে ফিরুন',
  'granted': 'অনুমোদিত',
  'Select all': 'সব বাছুন',
  'Clear all': 'সব মুছুন',
  'View': 'দেখা',
  'Create': 'তৈরি',
  'Delete': 'মোছা',
  'Take': 'নেওয়া',
  'Collect': 'আদায়',
  'Waive': 'মওকুফ',
  'Manage': 'পরিচালনা',
  'Publish': 'প্রকাশ',
  'Enter': 'এন্ট্রি',
  'Export': 'রপ্তানি',
  'Upload': 'আপলোড',
  'This person has their own permission list.':
    'এই ব্যক্তির নিজস্ব অনুমতির তালিকা আছে।',
  'This person follows their role’s preset.':
    'এই ব্যক্তি তাঁর রোলের ছক অনুসরণ করেন।',
  'A preset is a starting point. Once you save here, this list is the whole truth for this person — it is not merged with the preset, and changing the preset later will no longer move them. Use “Back to the preset” to undo that.':
    'রোলের ছক কেবল শুরুর বিন্দু। এখানে সেভ করার পর এই তালিকাটিই এই ব্যক্তির জন্য চূড়ান্ত — ছকের সঙ্গে এটি মেশানো হয় না, আর পরে ছক বদলালেও তাঁর কিছু বদলাবে না। ফিরে যেতে চাইলে “রোলের ছকে ফিরুন” চাপুন।',
  'Could not save these permissions.': 'এই অনুমতিগুলো সেভ করা যায়নি।',
  'The permission catalogue could not be loaded, so the checkboxes are unavailable.':
    'অনুমতির তালিকা আনা যায়নি, তাই চেকবক্সগুলো দেখানো যাচ্ছে না।',

  // ── Roles ───────────────────────────────────────────────────────────────
  'Add role': 'রোল যোগ করুন',
  'Edit role': 'রোল সম্পাদনা',
  'System preset': 'সিস্টেম ছক',
  'People on it': 'যতজন আছেন',
  'This role can be assigned': 'এই রোলটি দেওয়া যাবে',
  'This is a system preset.': 'এটি একটি সিস্টেম ছক।',
  'Its name cannot change — the seed and every account on it refer to the preset by name — and it cannot be deleted while people are on it. You can still adjust its permissions, or switch it off to retire it.':
    'এর নাম বদলানো যায় না — সিস্টেম ও এই ছকে থাকা প্রতিটি অ্যাকাউন্ট নাম ধরেই একে চেনে — আর কেউ এতে থাকলে মোছাও যায় না। তবে অনুমতিগুলো বদলাতে পারেন, কিংবা বন্ধ করে দিতে পারেন।',
  'Changing these moves everyone still on this preset. People whose permissions have been customised are left alone.':
    'এগুলো বদলালে যাঁরা এখনো এই ছকে আছেন সবার বদলাবে। যাঁদের অনুমতি আলাদা করে সাজানো হয়েছে, তাঁদের কিছু বদলাবে না।',
  'No roles yet.': 'এখনো কোনো রোল নেই।',
  'Could not load the roles.': 'রোলের তালিকা আনা যায়নি।',
  'Could not save this role.': 'এই রোলটি সেভ করা যায়নি।',

  // ── Live activity ───────────────────────────────────────────────────────
  'Live': 'সরাসরি',
  'Paused': 'থামানো',
  'Pause': 'থামান',
  'Resume': 'চালু করুন',
  'new': 'নতুন',
  'new entries are waiting. Tap to show them.':
    'নতুন এন্ট্রি অপেক্ষা করছে। দেখতে চাপুন।',
  'Money entries are tinted; failed logins and permission changes are flagged.':
    'টাকার এন্ট্রি রঙিন; ব্যর্থ লগইন ও অনুমতির পরিবর্তন আলাদা করে চিহ্নিত।',
  'All institutions': 'সব প্রতিষ্ঠান',
  'Everyone': 'সবাই',
  'Person': 'ব্যক্তি',
  'Action': 'কাজ',
  'All actions': 'সব কাজ',
  'Nothing yet.': 'এখনো কিছু নেই।',
  'Nothing yet today.': 'আজ এখনো কিছু নেই।',
  'The feed is not answering right now.': 'কার্যক্রমের তালিকা এখন সাড়া দিচ্ছে না।',
  'System': 'সিস্টেম',
  'Created': 'তৈরি হয়েছে',
  'Updated': 'হালনাগাদ হয়েছে',
  'Deleted': 'মুছে ফেলা হয়েছে',
  'Login': 'লগইন',
  'Failed login': 'ব্যর্থ লগইন',
  'Fee collected': 'ফি আদায়',
  'Fee waived': 'ফি মওকুফ',
  'Results published': 'ফলাফল প্রকাশ',
  'Attendance taken': 'হাজিরা নেওয়া',
  'Permission changed': 'অনুমতি বদল',
  'Role changed': 'রোল বদল',

  // ── Dashboard, phase 1 counts ───────────────────────────────────────────
  'On the platform': 'প্ল্যাটফর্মে',
  'Active logins': 'সক্রিয় লগইন',
  'Current sessions': 'চলমান শিক্ষাবর্ষ',
  'Academic years running now': 'এখন চলছে যে শিক্ষাবর্ষগুলো',
  'Student, attendance, fee and exam figures arrive with their modules.':
    'শিক্ষার্থী, হাজিরা, ফি ও পরীক্ষার সংখ্যাগুলো নিজ নিজ অংশের সঙ্গে আসবে।',
  // ── Settings → SMS ────────────────────────────────────────────────────
  SMS: 'এসএমএস',
  Sending: 'পাঠানো',
  'Send SMS to guardians': 'অভিভাবকদের এসএমএস পাঠানো হবে',
  'Off means nothing leaves this institution, whatever a screen offers.':
    'বন্ধ থাকলে কোনো পর্দা যা-ই দেখাক, এই প্রতিষ্ঠান থেকে কিছু যাবে না।',
  'Sender name': 'প্রেরকের নাম',
  'What the guardian sees the message is from. Registered with the SMS operator; left blank, the platform’s own name is used.':
    'অভিভাবক যে নামে বার্তাটি পাবেন। এসএমএস অপারেটরে নিবন্ধিত; খালি রাখলে প্ল্যাটফর্মের নাম যাবে।',
  'What a result message says': 'ফলের বার্তায় যা থাকবে',
  'SMS per student': 'এসএমএস প্রতি শিক্ষার্থী',
  'Bangla is sent as Unicode: 70 characters to one SMS.':
    'বাংলা ইউনিকোডে যায়: এক এসএমএসে ৭০ অক্ষর।',
  'English only: 160 characters to one SMS.': 'শুধু ইংরেজি: এক এসএমএসে ১৬০ অক্ষর।',
  'Use the default wording': 'ডিফল্ট বার্তা নিন',
  'Save message': 'বার্তা সংরক্ষণ',
  'Recently sent': 'সম্প্রতি পাঠানো',
  'Nothing has been sent yet.': 'এখনো কিছু পাঠানো হয়নি।',
  'Choose an institution in the header to set up its SMS.':
    'এসএমএস সেট করতে উপরের তালিকা থেকে একটি প্রতিষ্ঠান বাছুন।',
  'Could not load the SMS settings.': 'এসএমএস সেটিংস আনা যায়নি।',
  'The message could not be saved.': 'বার্তাটি সংরক্ষণ করা যায়নি।',
  'That could not be saved.': 'এটি সংরক্ষণ করা যায়নি।',
  Provider: 'সরবরাহকারী',
  'Send automatically': 'স্বয়ংক্রিয়ভাবে পাঠানো হবে',
  'When a student is admitted': 'শিক্ষার্থী ভর্তি হলে',
  'When a fee payment is taken': 'ফি জমা নেওয়া হলে',
  'What each message says': 'কোন বার্তায় যা থাকবে',
  Results: 'ফলাফল',
  Admission: 'ভর্তি',
  'Fee received': 'ফি জমা',
};
export default admin;
