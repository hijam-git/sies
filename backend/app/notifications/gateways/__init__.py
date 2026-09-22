"""The provider registry.

Add a provider by dropping a module here that subclasses `SmsGateway` and
naming it below. `settings.SMS_PROVIDER` picks the active one, and it defaults
to `console` — an install that has not been given credentials logs its messages
instead of spending money on them.
"""

from django.conf import settings

from .base import SmsGateway, SmsResult
from .bulksmsbd import BulkSmsBdGateway
from .console import ConsoleGateway

DEFAULT_PROVIDER = 'console'

_REGISTRY = {
    'console': ConsoleGateway,
    'bulksmsbd': BulkSmsBdGateway,
}


def get_sms_gateway(name: str | None = None) -> SmsGateway:
    """The active gateway.

    An unknown name falls back to the console rather than to a real provider:
    a typo in an environment variable must not be the thing that decides money
    is spent.
    """
    key = (name or getattr(settings, 'SMS_PROVIDER', DEFAULT_PROVIDER) or DEFAULT_PROVIDER).lower()
    return _REGISTRY.get(key, ConsoleGateway)()


__all__ = ['SmsGateway', 'SmsResult', 'get_sms_gateway', 'DEFAULT_PROVIDER']
