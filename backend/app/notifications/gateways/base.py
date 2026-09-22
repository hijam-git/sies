"""The adapter interface — docs/02 §4.9's "one adapter interface".

Ported from `~/awliaa/backend/app/notifications/sms_gateways/base.py`
(CLAUDE.md §3: copy the patterns). One change, and it is the important one:
`send()` takes the **sender id** as an argument rather than reading it off
settings, because in SIES the sender is a property of the *institution*
(`Branch.sms_sender_id`) and not of the platform. Awliaa has one shop per
deployment's worth of branding; SIES has a madrasah and a college sharing one
gateway account and needing different names on the handset.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SmsResult:
    """A provider's answer, normalised so nothing above this layer parses it."""

    success: bool
    code: str = ''       # the provider's own status code, e.g. '202'
    message: str = ''    # what that code means, in words
    raw: str = ''        # the untouched response body, for the audit trail


class SmsGateway(ABC):
    """Base class for SMS providers."""

    name: str = 'base'
    label: str = 'Base'

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True only when this provider's credentials are actually present."""

    @abstractmethod
    def send(self, *, to, body: str, sender_id: str = '') -> SmsResult:
        """Send one body to one number.

        **Implementations must never raise.** A provider that is unreachable,
        rate-limited or misconfigured returns `SmsResult(success=False, …)`; the
        caller decides whether that is worth a retry. An exception escaping here
        would land in a Celery task retrying a whole fan-out for one bad number.
        """

    def balance(self) -> SmsResult:
        """Optional: the credit left on the account. Default: unsupported."""
        return SmsResult(False, message='balance_not_supported')
