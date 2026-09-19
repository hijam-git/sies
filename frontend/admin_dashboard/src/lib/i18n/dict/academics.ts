// Bangla for the Academics screens: classes, sections, subjects, the bell
// schedule and the weekly routine.
//
// রুটিন is the word every Bangladeshi institution uses for a timetable; a
// literal সময়সূচি reads as a bus schedule.
const academics: Record<string, string> = {
  'Classes': 'শ্রেণিসমূহ',
  'Sections': 'শাখাসমূহ',
  'Routine': 'রুটিন',

  // ── Classes ────────────────────────────────────────────────────────────
  'Add class': 'শ্রেণি যোগ করুন',
  'Edit class': 'শ্রেণি সম্পাদনা',
  'No classes yet.': 'কোনো শ্রেণি নেই।',
  'Search by class name': 'শ্রেণির নাম দিয়ে খুঁজুন',
  'Choose a class': 'একটি শ্রেণি বাছুন',
  'Choose a session': 'একটি শিক্ষাবর্ষ বাছুন',
  'Choose a stream': 'একটি বিভাগ বাছুন',
  'Active and inactive': 'সক্রিয় ও নিষ্ক্রিয়',
  'Level order': 'শ্রেণিক্রম',
  'Where this class sits in the ladder — it is what promotion follows.':
    'শ্রেণিটি ধাপে কোথায় — উত্তীর্ণের ক্রম এটিই অনুসরণ করে।',
  'Capacity': 'ধারণক্ষমতা',
  'Monthly fee': 'মাসিক ফি',
  'Could not load the classes.': 'শ্রেণি তালিকা আনা যায়নি।',
  'Could not save this class.': 'শ্রেণিটি সংরক্ষণ করা যায়নি।',

  // ── Sections ───────────────────────────────────────────────────────────
  'Add section': 'শাখা যোগ করুন',
  'Edit section': 'শাখা সম্পাদনা',
  'Room': 'কক্ষ',
  'In charge': 'দায়িত্বপ্রাপ্ত',
  'This class has no sections yet.': 'এই শ্রেণিতে কোনো শাখা নেই।',
  'Choose a class to see its sections.': 'শাখা দেখতে একটি শ্রেণি বাছুন।',
  'Delete this section? Students already in it keep their enrolment.':
    'শাখাটি মুছবেন? এতে থাকা শিক্ষার্থীদের ভর্তি অক্ষত থাকবে।',
  'Could not load the sections.': 'শাখা তালিকা আনা যায়নি।',
  'Could not save this section.': 'শাখাটি সংরক্ষণ করা যায়নি।',
  'Could not delete this section.': 'শাখাটি মুছে ফেলা যায়নি।',

  // ── Subjects ───────────────────────────────────────────────────────────
  'Subject': 'বিষয়',
  'Add subject': 'বিষয় যোগ করুন',
  'Edit subject': 'বিষয় সম্পাদনা',
  'Full marks': 'পূর্ণমান',
  'Pass marks': 'পাস নম্বর',
  'Practical': 'ব্যবহারিক',
  'Practical marks': 'ব্যবহারিক নম্বর',
  'Has practical': 'ব্যবহারিক আছে',
  'Optional subject': 'ঐচ্ছিক বিষয়',
  'Not every student takes it': 'সব শিক্ষার্থী নেয় না',
  'Every stream': 'সব বিভাগ',
  'This class has no subjects yet.': 'এই শ্রেণিতে কোনো বিষয় নেই।',
  'Choose a class to see its subjects.': 'বিষয় দেখতে একটি শ্রেণি বাছুন।',
  'Add a class first — subjects belong to one.': 'আগে একটি শ্রেণি যোগ করুন — বিষয় শ্রেণির অধীনে থাকে।',
  'Delete this subject?': 'বিষয়টি মুছবেন?',
  'Could not load the subjects.': 'বিষয় তালিকা আনা যায়নি।',
  'Could not save this subject.': 'বিষয়টি সংরক্ষণ করা যায়নি।',
  'Could not delete this subject.': 'বিষয়টি মুছে ফেলা যায়নি।',

  // ── Periods, the bell schedule ─────────────────────────────────────────
  'Periods (bell schedule)': 'ঘণ্টা (ঘণ্টাসূচি)',
  'These times are the rows of every class’s week. Changing one moves that period for the whole institution.':
    'এই সময়গুলোই প্রতিটি শ্রেণির সপ্তাহের সারি। একটি বদলালে পুরো প্রতিষ্ঠানের ঐ ঘণ্টা সরে যায়।',
  'No periods yet — the routine grid has no rows until one exists.':
    'কোনো ঘণ্টা নেই — একটি না থাকা পর্যন্ত রুটিনে কোনো সারি থাকবে না।',
  'Add period': 'ঘণ্টা যোগ করুন',
  'Edit period': 'ঘণ্টা সম্পাদনা',
  'Add a period above before building the routine.': 'রুটিন সাজানোর আগে উপরে একটি ঘণ্টা যোগ করুন।',
  'Starts': 'শুরু',
  'Ends': 'শেষ',
  'Break': 'বিরতি',
  'Nothing is taught in this period': 'এই ঘণ্টায় কোনো পাঠ হয় না',
  'Leave blank when the whole institution rings the same bell.':
    'পুরো প্রতিষ্ঠানে একই ঘণ্টা বাজলে খালি রাখুন।',
  'Delete this period? Every lesson scheduled in it is removed with it.':
    'ঘণ্টাটি মুছবেন? এতে রাখা প্রতিটি পাঠও মুছে যাবে।',
  'Could not save this period.': 'ঘণ্টাটি সংরক্ষণ করা যায়নি।',
  'Could not delete this period.': 'ঘণ্টাটি মুছে ফেলা যায়নি।',

  // ── The routine grid ───────────────────────────────────────────────────
  'Whole class': 'পুরো শ্রেণি',
  'Choose a class to see its week.': 'সপ্তাহ দেখতে একটি শ্রেণি বাছুন।',
  'Choose a subject': 'একটি বিষয় বাছুন',
  'Choose a teacher': 'একজন শিক্ষক বাছুন',
  'Clear': 'মুছুন',
  'already teaches': 'ইতিমধ্যে পড়ান',
  'at this time.': 'এই সময়ে।',
  'Could not load the routine.': 'রুটিন আনা যায়নি।',
  'Could not save this lesson.': 'পাঠটি সংরক্ষণ করা যায়নি।',
  'Could not clear this lesson.': 'পাঠটি মুছে ফেলা যায়নি।',

  // ── Words the Overview and several tabs share ──────────────────────────
  'Loading…': 'লোড হচ্ছে…',
  'Saving…': 'সংরক্ষণ হচ্ছে…',
  'On the roll': 'তালিকাভুক্ত',
  'Currently teaching': 'বর্তমানে কর্মরত',
  'Across every stream': 'সব বিভাগ মিলিয়ে',
  'Attendance, fee and exam figures arrive with their modules.':
    'হাজিরা, ফি ও পরীক্ষার হিসাব নিজ নিজ মডিউলের সঙ্গে আসবে।',
  'Nothing is being hidden — the phases that raise fees, take attendance and publish results have not been built yet, so those figures are honestly zero.':
    'কিছু লুকানো হয়নি — ফি, হাজিরা ও ফলাফলের ধাপগুলো এখনো তৈরি হয়নি, তাই ঐ সংখ্যাগুলো সত্যিই শূন্য।',

  // ── My routine — a teacher's own week (docs/08 D7) ─────────────────────
  'Periods a week': 'সাপ্তাহিক পিরিয়ড',
  'Free': 'ফাঁকা',
  'Now': 'এখন',
  'Could not load your routine.': 'আপনার রুটিন আনা যায়নি।',
  'No classes have been assigned to you yet.':
    'আপনাকে এখনো কোনো ক্লাস দেওয়া হয়নি।',
  'The office builds the weekly routine under Academics → Routine. Ask them to add your periods.':
    'অফিস শিক্ষা কার্যক্রম → রুটিন থেকে সাপ্তাহিক রুটিন তৈরি করে। আপনার পিরিয়ডগুলো যোগ করতে বলুন।',
  'One class': 'এক শ্রেণি',
  'All classes': 'সব শ্রেণি',
  'All teachers': 'সব শিক্ষক',
  'Double-booked': 'একই সময়ে দুই ক্লাস',
  'Nothing is scheduled yet.': 'এখনো কোনো রুটিন তৈরি হয়নি।',
  'Could not load the bell schedule.': 'পিরিয়ড তালিকা আনা যায়নি।',
};

export default academics;
