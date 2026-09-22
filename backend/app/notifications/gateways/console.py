"""The gateway dev and staging run on: it writes the SMS to the log.

**This is the default provider**, and that is deliberate. Every other safety
switch in this module can be turned off by a setting; the one that matters is
that an install which has not been given credentials cannot spend money, and a
`seed_demo` database full of made-up phone numbers cannot text a stranger.

It reports success, so the outbox, the parts arithmetic and the screens can all
be exercised end to end without a gateway account.
"""

import logging

from .base import SmsGateway, SmsResult

logger = logging.getLogger(__name__)


class ConsoleGateway(SmsGateway):
    name = 'console'
    label = 'Console (writes to the log, sends nothing)'

    @property
    def is_configured(self) -> bool:
        return True

    def send(self, *, to, body: str, sender_id: str = '') -> SmsResult:
        logger.info('[SMS console] to=%s sender=%s body=%s', to, sender_id or '-', body)
        return SmsResult(True, code='console', message='logged, not sent')

    def balance(self) -> SmsResult:
        return SmsResult(True, message='console gateway has no balance')
