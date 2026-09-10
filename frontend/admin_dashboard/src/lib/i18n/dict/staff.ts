// Bangla for the Staff screens: teachers, other employees, and assignments.
//
// শিক্ষক and কর্মচারী are kept strictly apart, as the two models are (docs/08
// D5) — an institution says one or the other and never means both.
const staff: Record<string, string> = {
  'Teachers, other employees, and which classes each teacher covers.':
    'শিক্ষক, অন্যান্য কর্মচারী, এবং কোন শিক্ষক কোন শ্রেণি নেন।',
  'Assignments': 'দায়িত্ব বণ্টন',

  // ── Teachers ───────────────────────────────────────────────────────────
  'Everyone who teaches. Their classes are set on the Assignments tab.':
    'যারা পড়ান। তাদের শ্রেণি নির্ধারিত হয় দায়িত্ব বণ্টন ট্যাবে।',
  'Add teacher': 'শিক্ষক যোগ করুন',
  'Edit teacher': 'শিক্ষক সম্পাদনা',
  'No teachers yet.': 'কোনো শিক্ষক নেই।',
  'Search by name, ID or phone': 'নাম, আইডি বা মোবাইল দিয়ে খুঁজুন',
  'Could not load the teachers.': 'শিক্ষক তালিকা আনা যায়নি।',
  'Could not save this teacher.': 'শিক্ষকটি সংরক্ষণ করা যায়নি।',
  'Teaching': 'শিক্ষকতা',
  'Specialization': 'বিশেষজ্ঞতা',
  'Subjects': 'বিষয়',
  'Maximum weekly periods': 'সাপ্তাহিক সর্বোচ্চ ঘণ্টা',
  'Leave blank for no ceiling.': 'সীমা না থাকলে খালি রাখুন।',
  'May be a class teacher': 'শ্রেণিশিক্ষক হতে পারেন',
  'Qualifications': 'শিক্ষাগত যোগ্যতা',
  'Add qualification': 'যোগ্যতা যোগ করুন',
  'No qualifications recorded.': 'কোনো যোগ্যতা লেখা নেই।',
  'Degree': 'ডিগ্রি',
  'Result': 'ফলাফল',
  'Year': 'সাল',
  'Could not save this qualification.': 'যোগ্যতাটি সংরক্ষণ করা যায়নি।',
  'Could not delete this qualification.': 'যোগ্যতাটি মুছে ফেলা যায়নি।',

  // ── Employees ──────────────────────────────────────────────────────────
  'The office, the kitchen, the guard — everyone who is not a teacher.':
    'অফিস, রান্নাঘর, প্রহরী — যারা শিক্ষক নন।',
  'Add employee': 'কর্মচারী যোগ করুন',
  'Edit employee': 'কর্মচারী সম্পাদনা',
  'No employees yet.': 'কোনো কর্মচারী নেই।',
  'Search by name, ID or department': 'নাম, আইডি বা বিভাগ দিয়ে খুঁজুন',
  'Could not load the employees.': 'কর্মচারী তালিকা আনা যায়নি।',
  'Could not save this employee.': 'কর্মচারীটি সংরক্ষণ করা যায়নি।',
  'Department': 'বিভাগ',
  'Duty': 'দায়িত্ব',
  'Duty shift': 'কর্মপালা',

  // ── The shared person form ─────────────────────────────────────────────
  'Designation': 'পদবি',
  'Joining date': 'যোগদানের তারিখ',
  'Leaving date': 'প্রস্থানের তারিখ',
  'Alternate mobile': 'বিকল্প মোবাইল',
  'Employment status': 'চাকরির অবস্থা',
  'On leave': 'ছুটিতে',
  'Suspended': 'সাময়িক বরখাস্ত',
  'Resigned': 'পদত্যাগ',
  'Terminated': 'চাকরিচ্যুত',
  'Male': 'পুরুষ',
  'Female': 'মহিলা',
  'Pay': 'বেতন',
  'Basic salary': 'মূল বেতন',
  'Allowances': 'ভাতা',
  'Deductions': 'কর্তন',
  'Bank account': 'ব্যাংক হিসাব',
  'Mobile banking': 'মোবাইল ব্যাংকিং',
  'Emergency contact': 'জরুরি যোগাযোগ',
  'Other address details': 'ঠিকানার অন্যান্য বিবরণ',

  // ── Assignments (docs/08 D6) ───────────────────────────────────────────
  'An assignment is what a teacher can reach: attendance and marks are limited to the classes named here.':
    'দায়িত্ব বণ্টনই শিক্ষকের নাগাল ঠিক করে — হাজিরা ও নম্বর কেবল এখানে দেওয়া শ্রেণিতেই সীমাবদ্ধ।',
  'Choose a class to set its teachers.': 'শিক্ষক নির্ধারণ করতে একটি শ্রেণি বাছুন।',
  'Class teacher': 'শ্রেণিশিক্ষক',
  'Owns the daily register for this class and may correct a cell somebody else filled in.':
    'এই শ্রেণির দৈনিক হাজিরার দায়িত্ব তাঁর, এবং অন্যের দেওয়া ঘরও তিনি সংশোধন করতে পারেন।',
  'Subject teachers': 'বিষয়শিক্ষক',
  'Not assigned': 'নির্ধারিত নয়',
  'assigned': 'নির্ধারিত',
  'Could not load the assignments.': 'দায়িত্ব বণ্টন আনা যায়নি।',
  'Could not save this assignment.': 'দায়িত্বটি সংরক্ষণ করা যায়নি।',
  'Could not save the class teacher.': 'শ্রেণিশিক্ষক সংরক্ষণ করা যায়নি।',

  // ── The assignment board ───────────────────────────────────────────────
  'class teacher': 'শ্রেণিশিক্ষক',
  'Unassigned work': 'দায়িত্বহীন কাজ',
  'Nobody covers these yet.': 'এগুলোর দায়িত্বে এখনও কেউ নেই।',
  'Everything is assigned.': 'সব দায়িত্ব বণ্টন হয়েছে।',
  'Nothing assigned yet.': 'এখনও কোনো দায়িত্ব নেই।',
  'Nobody yet': 'এখনও কেউ নয়',
  'No class teacher yet': 'শ্রেণিশিক্ষক এখনও নেই',
  'Every class has a class teacher.': 'প্রতিটি শ্রেণিতে শ্রেণিশিক্ষক আছেন।',
  'Drag a card onto a teacher — or tap the card, then tap the teacher.':
    'কার্ডটি শিক্ষকের ওপর টেনে আনুন — অথবা কার্ডে চাপ দিয়ে তারপর শিক্ষকে চাপ দিন।',
  'assign here': 'এখানে দিন',
  'Now tap a teacher.': 'এবার একজন শিক্ষকে চাপ দিন।',
  'picked up. Choose a teacher.': 'হাতে নেওয়া হয়েছে। একজন শিক্ষক বাছুন।',
  'Cancelled.': 'বাতিল করা হয়েছে।',
  'That did not save — the card went back.': 'সংরক্ষণ হয়নি — কার্ডটি ফিরিয়ে দেওয়া হয়েছে।',
};

export default staff;
