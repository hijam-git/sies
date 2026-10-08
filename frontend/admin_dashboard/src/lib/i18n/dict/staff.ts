// Bangla for the Staff screens: teachers and other employees.
//
// শিক্ষক and কর্মচারী are kept strictly apart, as the two models are (docs/08
// D5) — an institution says one or the other and never means both.
const staff: Record<string, string> = {
  'Teachers, other employees, and which classes each teacher covers.':
    'শিক্ষক, অন্যান্য কর্মচারী, এবং কোন শিক্ষক কোন শ্রেণি নেন।',
  'Assignments': 'দায়িত্ব বণ্টন',

  // ── Teachers ───────────────────────────────────────────────────────────
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

  // ── Assignment wording still used by the class, section and routine screens
  'Class teacher': 'শ্রেণিশিক্ষক',
  'class teacher': 'শ্রেণিশিক্ষক',
  'Not assigned': 'নির্ধারিত নয়',
  'assigned': 'নির্ধারিত',
};

export default staff;
