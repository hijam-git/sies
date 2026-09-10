"""Canonicalising a Bangladeshi mobile number.

Load-bearing, because **the phone IS the login** (CLAUDE.md §1). A counter clerk
who types `+8801712345678` and the principal who typed `01712-345678` when
creating the account are naming the same person, and that person has exactly one
row. Compared as raw text they are three different people, and the third one
cannot log in.

This module is deliberately tiny and dependency-free so it can be read
side-by-side with the SPA's `src/lib/normalizeBdPhone.ts`. The two must agree
character for character; they are the same rule written twice because one runs
before the request is sent and the other decides what is stored.
"""

import re

# A BD mobile: `01`, an operator digit 3-9, then eight more. The operator digit
# is checked rather than accepting any `01…`, because `012…` is not a number
# anyone can be reached on and an account keyed to one is an account whose owner
# can never be sent a password.
BD_MOBILE_RE = re.compile(r'^01[3-9]\d{8}$')

_NON_DIGITS = re.compile(r'\D')

# Both messages travel to the SPA; `invalid_phone` is what it switches on
# (docs/WORKLOG F15) and the English is only the fallback.
INVALID_PHONE_MESSAGE = 'Enter an 11-digit mobile number, e.g. 01712345678.'
INVALID_PHONE_MESSAGE_BN = '১১ ডিজিটের মোবাইল নম্বর দিন, যেমন ০১৭১২৩৪৫৬৭৮।'


def normalize_bd_phone(raw):
    """`'+88 01712-345678'` → `'01712345678'`.

    Returns `''` — not the input, and not None — for anything that is not a BD
    mobile. An empty string is falsy and cannot be mistaken for a number, so a
    caller that forgets to check compares against nothing rather than against a
    landline it half-cleaned.
    """
    digits = _NON_DIGITS.sub('', raw or '')

    # `+880…` and `880…` collapse to the same thing once the punctuation is
    # gone, so the country code is stripped once here rather than twice.
    if digits.startswith('88'):
        digits = digits[2:]

    # Written internationally the leading zero is dropped (`1712345678`). Put it
    # back before matching, or every number copied out of a WhatsApp contact
    # fails.
    if len(digits) == 10 and digits.startswith('1'):
        digits = '0' + digits

    return digits if BD_MOBILE_RE.match(digits) else ''


def is_valid_bd_phone(raw):
    """True when *raw* canonicalises to a real BD mobile."""
    return bool(normalize_bd_phone(raw))
