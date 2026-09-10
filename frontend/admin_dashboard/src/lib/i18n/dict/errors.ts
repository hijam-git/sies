// Bangla for the error sentences in lib/apiErrors.ts. Keys must match that
// file's English exactly — it is the dictionary key, not a separate copy.
const errors: Record<string, string> = {
  'Enter an 11-digit mobile number, e.g. 01712345678.':
    '১১ সংখ্যার মোবাইল নম্বর লিখুন, যেমন ০১৭১২৩৪৫৬৭৮।',
  'This phone number and password do not match an account.':
    'এই মোবাইল নম্বর ও পাসওয়ার্ড কোনো অ্যাকাউন্টের সঙ্গে মিলছে না।',
  'This account has been switched off. Ask your institution\'s admin.':
    'এই অ্যাকাউন্টটি বন্ধ করে দেওয়া হয়েছে। আপনার প্রতিষ্ঠানের অ্যাডমিনের সঙ্গে যোগাযোগ করুন।',
  'Could not sign in. Please try again.': 'লগইন করা যায়নি। আবার চেষ্টা করুন।',

  'You do not have permission to do this.': 'এই কাজটি করার অনুমতি আপনার নেই।',
  'That record does not exist, or it belongs to another institution.':
    'এই তথ্যটি নেই, অথবা এটি অন্য প্রতিষ্ঠানের।',
  'This class is not one of yours. Ask the admin to assign it to you.':
    'এই ক্লাসটি আপনার দায়িত্বে নেই। অ্যাডমিনকে বলে দায়িত্ব নিন।',

  'This fee has already been collected in full.': 'এই ফি ইতিমধ্যেই পুরোপুরি আদায় হয়েছে।',
  'That is more than is outstanding on this fee.': 'এই ফিতে যত বকেয়া আছে, এটি তার চেয়ে বেশি।',
  'This receipt has already been reversed.': 'এই রসিদটি ইতিমধ্যেই বাতিল করা হয়েছে।',

  'The time for taking this period\'s attendance has passed. A class teacher or the principal can still fill it in.':
    'এই ঘণ্টার হাজিরা নেওয়ার সময় পেরিয়ে গেছে। শ্রেণি শিক্ষক বা প্রধান এখনো এটি পূরণ করতে পারবেন।',
  'Results for this exam are published, so marks can no longer be changed.':
    'এই পরীক্ষার ফলাফল প্রকাশিত হয়ে গেছে, তাই নম্বর আর বদলানো যাবে না।',

  'Something with this name or number already exists.': 'এই নাম বা নম্বরে ইতিমধ্যেই একটি আছে।',
  'Other records point at this one, so it cannot be deleted. Switch it off instead.':
    'অন্য তথ্য এটির সঙ্গে যুক্ত, তাই এটি ডিলিট করা যাবে না। বরং নিষ্ক্রিয় করে দিন।',

  'Something went wrong. Please try again.': 'কোনো সমস্যা হয়েছে। আবার চেষ্টা করুন।',
};
export default errors;
