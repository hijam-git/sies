// Bangla for the attendance screens: the month register, the period roster and
// the teacher's today board.
//
// হাজিরা is the word used in every Bangladeshi institution's register — not
// উপস্থিতি, which is the abstract noun and reads as a statistic rather than as
// the thing a teacher takes each morning.
const attendance: Record<string, string> = {
  'Another class': 'অন্য ক্লাস',
  'Now': 'এখন',
  'Attendance': 'হাজিরা',
  'Month register': 'মাসিক খাতা',
  'Class attendance': 'ক্লাস হাজিরা',
  'Could not load the register.': 'হাজিরা খাতা লোড করা যায়নি।',
  'Could not save the register.': 'হাজিরা খাতা সেভ করা যায়নি।',
  'Could not load the roster.': 'শিক্ষার্থী তালিকা লোড করা যায়নি।',
  'Could not save attendance.': 'হাজিরা সেভ করা যায়নি।',

  // ── The register ───────────────────────────────────────────────────────
  'Student': 'শিক্ষার্থী',
  'Month': 'মাস',
  'Whole class': 'পুরো শ্রেণি',
  'Previous month': 'আগের মাস',
  'Next month': 'পরের মাস',
  'Previous day': 'আগের দিন',
  'Next day': 'পরের দিন',
  'Grid view': 'গ্রিড ভিউ',
  'Single day': 'একদিনের তালিকা',
  'Mark whole day present': 'সবাইকে উপস্থিত দিন',
  'All present': 'সবাই উপস্থিত',
  'All absent': 'সবাই অনুপস্থিত',
  'Not marked': 'চিহ্নিত হয়নি',
  'unsaved cells': 'ঘর সেভ হয়নি',
  'Discard': 'বাতিল করুন',
  'Saved': 'সেভ হয়েছে',
  'Not saved': 'সেভ হয়নি',
  'You can read this register but not change it.':
    'আপনি খাতা দেখতে পারবেন, পরিবর্তন করতে পারবেন না।',
  'No students are enrolled in this class.': 'এই শ্রেণিতে কোনো শিক্ষার্থী ভর্তি নেই।',
  'No classes are assigned to you.': 'আপনার নামে কোনো শ্রেণি নির্ধারিত নেই।',
  'No periods are set up yet.': 'এখনো কোনো পিরিয়ড নির্ধারণ করা হয়নি।',
  'Arrow keys move · P present · A absent · L leave · H holiday · Enter next student':
    'তীর চিহ্নে ঘর বদল · P উপস্থিত · A অনুপস্থিত · L ছুটি · H সরকারি ছুটি · Enter পরের শিক্ষার্থী',

  // ── Statuses ───────────────────────────────────────────────────────────
  'Present': 'উপস্থিত',
  'Absent': 'অনুপস্থিত',
  'Late': 'বিলম্বে উপস্থিত',
  'Leave': 'ছুটি',
  'Half day': 'অর্ধদিবস',
  'Holiday': 'সরকারি ছুটি',

  // ── Weekday abbreviations, as the column header shows them ─────────────
  'Sat': 'শনি',
  'Sun': 'রবি',
  'Mon': 'সোম',
  'Tue': 'মঙ্গল',
  'Wed': 'বুধ',
  'Thu': 'বৃহঃ',
  'Fri': 'শুক্র',

  // ── Period roster ──────────────────────────────────────────────────────
  'Already recorded': 'আগেই নেওয়া হয়েছে',
  'Not recorded': 'উল্লেখ করা হয়নি',
  'Submit attendance': 'হাজিরা জমা দিন',

  // ── The teacher's day board ────────────────────────────────────────────
  'Today’s classes': 'আজকের ক্লাস',
  'Could not load today’s classes.': 'আজকের ক্লাস লোড করা যায়নি।',
  'Nothing is scheduled for you on this day.': 'এই দিনে আপনার কোনো ক্লাস নেই।',
  'Take attendance': 'হাজিরা নিন',
  'Correct attendance': 'হাজিরা সংশোধন করুন',
  'Attendance for this period cannot be taken now.': 'এখন এই পিরিয়ডের হাজিরা নেওয়া যাবে না।',
  'students': 'জন শিক্ষার্থী',
  'taken': 'নেওয়া হয়েছে',
  'Taken': 'নেওয়া হয়েছে',
  'Live now': 'এখন চলছে',
  'Upcoming': 'আসন্ন',
  'Missed': 'বাদ পড়েছে',
  'You have unsaved attendance on this grid. Leave it?':
      'এই গ্রিডে সংরক্ষণ না করা হাজিরা রয়েছে। বাদ দিয়ে চলে যাবেন?',
  'Choose an institution in the header to take or read attendance.':
    'হাজিরা নিতে বা দেখতে উপরের তালিকা থেকে একটি প্রতিষ্ঠান বাছুন।',
};

export default attendance;
