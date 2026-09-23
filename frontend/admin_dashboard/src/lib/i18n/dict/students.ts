// Bangla for the Students screens: the roll, a student's record, and the
// admission process.
//
// The words are the ones a Bangladeshi office actually uses: ভর্তি for an
// admission, শিক্ষার্থী for a student, অভিভাবক for a guardian. A literal
// translation of "application" as আবেদনপত্র reads as the sheet of paper rather
// than the record, so আবেদন is used for the record and its number.
const students: Record<string, string> = {
  // ── The page and its tabs ──────────────────────────────────────────────
  'Admissions': 'ভর্তি',

  // ── The list ───────────────────────────────────────────────────────────
  'Student ID': 'শিক্ষার্থী আইডি',
  'Stream': 'বিভাগ',
  'Class': 'শ্রেণি',
  'Section': 'শাখা',
  'Roll': 'রোল',
  'Guardian': 'অভিভাবক',
  'Guardians': 'অভিভাবকগণ',
  'Not enrolled': 'ভর্তি হয়নি',
  'Open': 'খুলুন',
  'Add student': 'শিক্ষার্থী যোগ করুন',
  'Edit student': 'শিক্ষার্থী সম্পাদনা',
  'No students match this.': 'এই শর্তে কোনো শিক্ষার্থী নেই।',
  'Search by name, student ID or phone': 'নাম, আইডি বা মোবাইল দিয়ে খুঁজুন',
  'Every class': 'সব শ্রেণি',
  'Every section': 'সব শাখা',
  'Every status': 'সব অবস্থা',
  'All streams': 'সব বিভাগ',
  'All sessions': 'সব শিক্ষাবর্ষ',
  'Session': 'শিক্ষাবর্ষ',
  'Could not load the students.': 'শিক্ষার্থী তালিকা আনা যায়নি।',

  // ── Status ─────────────────────────────────────────────────────────────
  'Passed out': 'উত্তীর্ণ',
  'Withdrawn': 'ছাড়পত্রপ্রাপ্ত',
  'Transferred': 'স্থানান্তরিত',

  // ── The form ───────────────────────────────────────────────────────────
  'Date of birth': 'জন্ম তারিখ',
  'Gender': 'লিঙ্গ',
  'Boy': 'ছেলে',
  'Girl': 'মেয়ে',
  'Other': 'অন্যান্য',
  'Not stated': 'উল্লেখ নেই',
  'Blood group': 'রক্তের গ্রুপ',
  'Birth certificate no.': 'জন্ম নিবন্ধন নম্বর',
  'NID': 'জাতীয় পরিচয়পত্র',
  'Mobile': 'মোবাইল',
  'Most students have none. Leave it blank — a login is a separate action on the record.':
    'বেশির ভাগ শিক্ষার্থীর মোবাইল নেই। খালি রাখুন — লগইন আলাদা একটি কাজ।',
  'Village / area': 'গ্রাম / এলাকা',
  'Post office': 'ডাকঘর',
  'Upazila / thana': 'উপজেলা / থানা',
  'Four separate boxes, because the printed admission form has a line for each.':
    'চারটি আলাদা ঘর — ছাপা ভর্তি ফরমে প্রতিটির জন্য আলাদা লাইন আছে।',
  'Present address': 'বর্তমান ঠিকানা',
  'Permanent address': 'স্থায়ী ঠিকানা',
  'Previous schooling': 'পূর্ববর্তী শিক্ষা',
  'Previous institution': 'পূর্ববর্তী প্রতিষ্ঠান',
  'Previous class': 'পূর্ববর্তী শ্রেণি',
  'Previous result': 'পূর্ববর্তী ফলাফল',
  'Admitted on': 'ভর্তির তারিখ',
  'Record is in use': 'রেকর্ডটি ব্যবহারে আছে',
  'Photograph': 'ছবি',
  'Saved once the record exists.': 'রেকর্ড তৈরি হলে সংরক্ষিত হবে।',
  'Could not save this student.': 'শিক্ষার্থীটি সংরক্ষণ করা যায়নি।',

  // ── The record ─────────────────────────────────────────────────────────
  'Could not load this student.': 'শিক্ষার্থীর তথ্য আনা যায়নি।',
  'Enable login': 'লগইন চালু করুন',
  'Optional. Most students are admitted without a phone, so a login is an action on the record and never a step in admission.':
    'ঐচ্ছিক। বেশির ভাগ শিক্ষার্থী মোবাইল ছাড়াই ভর্তি হয়, তাই লগইন রেকর্ডের উপর একটি কাজ — ভর্তির ধাপ নয়।',
  'This student can sign in with': 'এই শিক্ষার্থী সাইন ইন করতে পারে —',
  'Could not create a login for this student.': 'এই শিক্ষার্থীর লগইন তৈরি করা যায়নি।',
  'Relation': 'সম্পর্ক',
  'Father': 'পিতা',
  'Mother': 'মাতা',
  'Brother': 'ভাই',
  'father': 'পিতা',
  'mother': 'মাতা',
  'brother': 'ভাই',
  'other': 'অন্যান্য',
  'Add guardian': 'অভিভাবক যোগ করুন',
  'No guardian recorded.': 'কোনো অভিভাবক যুক্ত নেই।',
  'A number already on file attaches this student to that guardian — which is how siblings share one record.':
    'নম্বরটি আগে থেকে থাকলে শিক্ষার্থীটি ঐ অভিভাবকের সঙ্গে যুক্ত হবে — ভাইবোন এভাবেই এক রেকর্ড ভাগ করে।',
  'Could not save this guardian.': 'অভিভাবক সংরক্ষণ করা যায়নি।',
  'Enrolment history': 'ভর্তির ইতিহাস',
  'One row per session — this is the admission history, not a separate record.':
    'প্রতি শিক্ষাবর্ষে একটি সারি — এটিই ভর্তির ইতিহাস, আলাদা কোনো রেকর্ড নয়।',
  'Not enrolled in any session yet.': 'এখনো কোনো শিক্ষাবর্ষে ভর্তি হয়নি।',
  'Documents': 'কাগজপত্র',
  'Document type': 'কাগজের ধরন',
  'No documents yet.': 'কোনো কাগজ নেই।',
  'Download': 'ডাউনলোড',
  'File': 'ফাইল',
  'Title': 'শিরোনাম',
  'Could not upload this document.': 'কাগজটি আপলোড করা যায়নি।',
  'Birth certificate': 'জন্ম নিবন্ধন',
  'Testimonial': 'প্রশংসাপত্র',
  'Transfer certificate': 'ছাড়পত্র',
  'Marksheet': 'নম্বরপত্র',
  'Certificate': 'সনদ',

  // ── Admissions ─────────────────────────────────────────────────────────
  'New application': 'নতুন আবেদন',
  'Edit application': 'আবেদন সম্পাদনা',
  'Applicant': 'আবেদনকারী',
  'Applied for class': 'যে শ্রেণিতে আবেদন',
  'Applied on': 'আবেদনের তারিখ',
  'Guardian name': 'অভিভাবকের নাম',
  'Guardian mobile': 'অভিভাবকের মোবাইল',
  'The number the institution calls, and where fee reminders go.':
    'প্রতিষ্ঠান এই নম্বরেই যোগাযোগ করে এবং ফি-র বার্তা পাঠায়।',
  'Remarks': 'মন্তব্য',
  'Search by applicant, application no. or guardian': 'আবেদনকারী, আবেদন নম্বর বা অভিভাবক দিয়ে খুঁজুন',
  'No applications yet.': 'কোনো আবেদন নেই।',
  'Could not load the applications.': 'আবেদন তালিকা আনা যায়নি।',
  'Could not save this application.': 'আবেদনটি সংরক্ষণ করা যায়নি।',
  'Pending': 'অপেক্ষমাণ',
  'Interview': 'সাক্ষাৎকার',
  'Accepted': 'নির্বাচিত',
  'Rejected': 'অনির্বাচিত',
  'Admitted': 'ভর্তি সম্পন্ন',
  'Cancelled': 'বাতিল',

  'Admit': 'ভর্তি করুন',
  'Admitting…': 'ভর্তি করা হচ্ছে…',
  'Leave blank and the next roll is allocated.': 'খালি রাখলে পরবর্তী রোল নম্বর দেওয়া হবে।',
  'Lives in the hostel': 'হোস্টেলে থাকে',
  'Uses the transport': 'পরিবহন ব্যবহার করে',
  'One step: the student record, the enrolment, the guardian and the numbers are all created together, or none of them are.':
    'এক ধাপ: শিক্ষার্থী, ভর্তি, অভিভাবক ও নম্বরগুলো একসঙ্গে তৈরি হয়, নয়তো কিছুই হয় না।',
  'is admitted.': 'ভর্তি সম্পন্ন হয়েছে।',
  'Admission no.': 'ভর্তি নম্বর',
  'A login is not part of this. Open the student record to give them one.':
    'লগইন এর অংশ নয়। প্রয়োজনে শিক্ষার্থীর রেকর্ড খুলে চালু করুন।',
  'Could not admit this applicant.': 'আবেদনকারীকে ভর্তি করা যায়নি।',

  // What the applicant hands across the counter, at the moment they hand it.
  'Papers handed in': 'জমা দেওয়া কাগজপত্র',
  'Taken now or picked from the gallery. It goes on the student record and on the admission form.':
    'এখনই তোলা যাবে বা গ্যালারি থেকে বেছে নেওয়া যাবে। ছবিটি শিক্ষার্থীর রেকর্ড ও ভর্তি ফরমে যুক্ত হবে।',
  'Add a certificate': 'সনদ যোগ করুন',
  'Left blank, the type is used.': 'খালি রাখলে কাগজের ধরনটিই শিরোনাম হবে।',
  'Certificates need the documents permission. The admission itself does not.':
    'সনদ সংরক্ষণের জন্য কাগজপত্রের অনুমতি লাগে; ভর্তির জন্য লাগে না।',
  'papers were filed with this admission.': 'টি কাগজ এই ভর্তির সঙ্গে সংরক্ষিত হয়েছে।',
  'The papers were not stored — your role may admit but may not file documents. Ask an administrator to add them to the student record.':
    'কাগজগুলো সংরক্ষণ করা হয়নি — আপনার ভূমিকা ভর্তি করতে পারে, কিন্তু কাগজপত্র জমা দিতে পারে না। প্রশাসককে বলে শিক্ষার্থীর রেকর্ডে যুক্ত করান।',
  'Could not load the class list.': 'শ্রেণি তালিকা আনা যায়নি।',
};

export default students;
