"""BulkSMSBD (https://bulksmsbd.net) — the Bangladeshi gateway.

Ported from `~/awliaa/backend/app/notifications/sms_gateways/bulksmsbd.py`,
which has been sending real SMS for real shops; the status-code table is the
provider's own and is the reason a failure here reads as "Balance Insufficient"
rather than as a 400.

    POST {base}/smsapi?api_key=..&type=text&senderid=..&number=..&message=..
    GET  {base}/getBalanceApi?api_key=..

Changed from the original: the sender id is passed in per message (see
`base.py`), and the HTTP call is `urllib` rather than `requests`. SIES does not
depend on `requests` and one form POST does not earn a dependency (CLAUDE.md §8
rule 7) — the dependency list is meant to stay short enough to read.

A masked Bengali sender is the normal case here, so code 1012, "Masking SMS
must be sent in Bengali", is a real answer an institution will meet if it
registers a masked sender and then writes its template in English.
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from .base import SmsGateway, SmsResult

logger = logging.getLogger(__name__)

TIMEOUT = 15
SUCCESS_CODE = '202'

#: The provider's published response codes.
STATUS_CODES = {
    '202': 'SMS Submitted Successfully',
    '1001': 'Invalid Number',
    '1002': 'Sender id not correct / sender id is disabled',
    '1003': 'Please required all fields / contact your system administrator',
    '1005': 'Internal Error',
    '1006': 'Balance Validity Not Available',
    '1007': 'Balance Insufficient',
    '1011': 'User Id not found',
    '1012': 'Masking SMS must be sent in Bengali',
    '1013': 'Sender Id has not found Gateway by api key',
    '1014': 'Sender Type Name not found using this sender by api key',
    '1015': 'Sender Id has not found Any Valid Gateway by api key',
    '1016': 'Sender Type Name Active Price Info not found by this sender id',
    '1017': 'Sender Type Name Price Info not found by this sender id',
    '1018': 'The Owner of this Account is disabled',
    '1019': 'The Price of this Account is disabled',
    '1020': 'The parent of this account is not found',
    '1021': 'The parent active price of this account is not found',
    '1031': 'Your Account Not Verified, Please Contact Administrator',
    '1032': 'IP Not whitelisted',
}


def _post(url: str, payload: dict) -> str:
    """One form POST, decoded as text. UTF-8 because the body is Bengali."""
    data = urllib.parse.urlencode(payload).encode('utf-8')
    request = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode('utf-8', errors='replace')


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        return response.read().decode('utf-8', errors='replace')


def to_gateway_number(raw) -> str:
    """`01711…`, `+8801711…`, `8801711…` → `8801711…` (no plus, digits only)."""
    digits = re.sub(r'[^0-9]', '', str(raw or ''))
    if digits.startswith('880'):
        return digits
    if digits.startswith('0'):
        return '88' + digits
    if digits.startswith('1') and len(digits) == 10:
        return '880' + digits
    return digits


def extract_code(raw: str) -> str:
    """The numeric status code, from JSON or from a bare number in the body."""
    raw = (raw or '').strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return str(data.get('response_code', data.get('code', ''))).strip()
    except (ValueError, TypeError):
        pass
    match = re.search(r'\b(\d{3,4})\b', raw)
    return match.group(1) if match else ''


class BulkSmsBdGateway(SmsGateway):
    name = 'bulksmsbd'
    label = 'BulkSMSBD (Bangladesh)'

    def __init__(self):
        self.api_key = getattr(settings, 'BULKSMSBD_API_KEY', '') or ''
        self.default_sender_id = getattr(settings, 'SMS_SENDER_ID', '') or ''
        self.base_url = (
            getattr(settings, 'BULKSMSBD_BASE_URL', '') or 'https://bulksmsbd.net/api'
        ).rstrip('/')

    @property
    def is_configured(self) -> bool:
        # The sender id is per branch, so only the key is platform-level. A
        # branch with no sender id of its own falls back to the platform's.
        return bool(self.api_key)

    def send(self, *, to, body: str, sender_id: str = '') -> SmsResult:
        if not self.is_configured:
            return SmsResult(False, message='bulksmsbd_not_configured')

        number = to_gateway_number(to)
        if not number:
            return SmsResult(False, message='no_valid_number')

        payload = {
            'api_key': self.api_key,
            'type': 'text',
            'senderid': sender_id or self.default_sender_id,
            'number': number,
            'message': body,
        }
        try:
            raw = _post(f'{self.base_url}/smsapi', payload)
        except (urllib.error.URLError, OSError) as exc:
            # Never raised upward: an unreachable gateway is a retry, and the
            # caller is the one holding the outbox row that records it.
            logger.warning('BulkSMSBD send failed: %s', exc)
            return SmsResult(False, message='gateway_unreachable')

        code = extract_code(raw)
        success = code == SUCCESS_CODE
        message = STATUS_CODES.get(code, 'Unknown response')
        if not success:
            logger.error('BulkSMSBD error: code=%s msg=%s raw=%s', code, message, raw[:300])
        return SmsResult(success, code=code, message=message, raw=raw)

    def balance(self) -> SmsResult:
        if not self.is_configured:
            return SmsResult(False, message='bulksmsbd_not_configured')
        query = urllib.parse.urlencode({'api_key': self.api_key})
        try:
            raw = _get(f'{self.base_url}/getBalanceApi?{query}')
        except (urllib.error.URLError, OSError) as exc:
            logger.warning('BulkSMSBD balance check failed: %s', exc)
            return SmsResult(False, message='gateway_unreachable')
        return SmsResult(True, raw=raw, message=raw.strip())
