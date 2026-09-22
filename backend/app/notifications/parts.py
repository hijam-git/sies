"""How many SMS one message costs.

This is billing arithmetic, so it is its own module with its own tests.

A GSM-7 message fits 160 characters in one part and 153 per part once it is
concatenated (the header eats seven). **Anything outside the GSM-7 alphabet —
every Bengali message this system sends — is UCS-2: 70 characters per part, 67
concatenated.** That is a factor of more than two, and getting it wrong means an
institution is quoted a price less than half of what the gateway charges. The
reference implementation this was ported from divided by 160 unconditionally,
which is right for English and wrong for every message SIES actually sends.
"""

#: The GSM 03.38 basic alphabet. A message made only of these characters is
#: sent as GSM-7; one character outside it moves the whole message to UCS-2.
GSM7_BASIC = set(
    '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?'
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'
)

#: These count as two characters each — they are sent as an escape plus a
#: character. Rare in this system's messages, but a body pasted from a keyboard
#: with a euro sign should not be under-counted.
GSM7_EXTENDED = set('^{}\\[~]|€')

SINGLE_GSM7, MULTI_GSM7 = 160, 153
SINGLE_UCS2, MULTI_UCS2 = 70, 67


def is_gsm7(body: str) -> bool:
    return all(ch in GSM7_BASIC or ch in GSM7_EXTENDED for ch in body or '')


def sms_length(body: str) -> int:
    """Billable length: GSM-7 extended characters count twice."""
    body = body or ''
    if not is_gsm7(body):
        return len(body)
    return sum(2 if ch in GSM7_EXTENDED else 1 for ch in body)


def sms_parts(body: str) -> int:
    """How many SMS the gateway will charge for this body.

    An empty body is one part, not zero: nothing here ever sends an empty
    message, and a zero would quietly make a bug free.
    """
    length = sms_length(body)
    single, multi = (SINGLE_GSM7, MULTI_GSM7) if is_gsm7(body or '') else (SINGLE_UCS2, MULTI_UCS2)
    if length <= single:
        return 1
    # Ceiling division, with the concatenation header counted in every part.
    return (length + multi - 1) // multi


def sms_cost(body: str) -> dict:
    """What the compose screen shows: characters, the limit, and the parts."""
    gsm = is_gsm7(body or '')
    single, multi = (SINGLE_GSM7, MULTI_GSM7) if gsm else (SINGLE_UCS2, MULTI_UCS2)
    parts = sms_parts(body)
    return {
        'characters': sms_length(body),
        'encoding': 'gsm7' if gsm else 'unicode',
        'per_part': single if parts == 1 else multi,
        'parts': parts,
    }
