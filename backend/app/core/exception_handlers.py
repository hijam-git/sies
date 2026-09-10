"""One error shape for the entire API (CLAUDE.md §5).

    {"success": false, "message": "...", "errors": {...}, "code": "..."}

Every failure the SPA can meet looks like this, so `lib/apiErrors.ts` has one
branch instead of one per endpoint: DRF's field errors, a permission denial, a
404, and the database integrity errors that reach the boundary because nobody
wrote a check for them.

`errors` carries the per-field detail a form needs to light up an input, and is
`{}` when there is none. `code` is the stable machine string the SPA translates
into Bangla; `message` is the English fallback for anything that has no
translation yet. Both are always present — a client that only knows one of them
still works.

Adapted from awliaa/backend/app/core/exception_handlers.py, which returned DRF's
own body unchanged and only reshaped IntegrityError. Here everything is reshaped,
because SIES has one client and it is ours: a single shape is worth more than
compatibility with DRF's default.
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

UNIQUE_VIOLATION_SQLSTATE = '23505'
FOREIGN_KEY_VIOLATION_SQLSTATE = '23503'

DUPLICATE_MESSAGE = 'That would duplicate something that already exists.'
PROTECTED_MESSAGE = (
    'This record is referenced by others and cannot be deleted. '
    'Deactivate it instead.'
)

# Codes the SPA switches on. Kept together so a new one is added deliberately.
CODE_VALIDATION = 'validation_error'
CODE_AUTHENTICATION = 'authentication_failed'
CODE_PERMISSION = 'permission_denied'
CODE_NOT_FOUND = 'not_found'
CODE_DUPLICATE = 'duplicate'
# 'protected_reference', not 'protected': the SPA's apiErrors.ts maps codes to
# Bangla and English messages, and a code it does not know falls back to a
# generic sentence. The vocabulary is a contract between the two halves
# (worklog F15), so the name here has to match the name there exactly.
CODE_PROTECTED = 'protected_reference'
CODE_ERROR = 'error'

_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: CODE_VALIDATION,
    status.HTTP_401_UNAUTHORIZED: CODE_AUTHENTICATION,
    status.HTTP_403_FORBIDDEN: CODE_PERMISSION,
    status.HTTP_404_NOT_FOUND: CODE_NOT_FOUND,
}


def _sqlstate(exc):
    """The database's own error code, or None if there is not one.

    Django wraps the driver's exception; the original is the `__cause__`.
    psycopg 3 exposes `.sqlstate`, psycopg2 `.pgcode`.
    """
    cause = getattr(exc, '__cause__', None) or exc
    return getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)


def _flatten(detail):
    """DRF's `detail` split into a message and a per-field mapping.

    A dict is field errors — the first one becomes the message so a toast has
    something to say without the caller digging. A list or a bare string has no
    field to attach to, so `errors` stays empty rather than inventing a key.
    """
    if isinstance(detail, dict):
        # DRF wraps every non-field exception as {'detail': ...}. That is not a
        # field, and leaving it in `errors` makes a form hunt for an input named
        # "detail". Its text is already the message.
        if set(detail) == {'detail'}:
            value = detail['detail']
            return str(value[0] if isinstance(value, list) else value), {}

        errors = {
            field: value if isinstance(value, list) else [value]
            for field, value in detail.items()
        }
        first = next(iter(errors.values()), None)
        message = str(first[0]) if first else 'Request failed.'
        return message, errors

    if isinstance(detail, list):
        return (str(detail[0]) if detail else 'Request failed.'), {}

    return str(detail), {}


def _envelope(message, errors, code, status_code):
    return Response(
        {'success': False, 'message': message, 'errors': errors, 'code': code},
        status=status_code,
    )


def api_exception_handler(exc, context):
    """DRF's handler first, then the exceptions it declines.

    Anything this function returns None for becomes a 500 with a traceback in the
    logs, which is the honest answer to a bug in our own code. Only failures a
    client can act on are turned into a shaped response.
    """
    # Django's own exceptions are the ones DRF converts before doing anything
    # else; converting them here first keeps the two paths identical.
    if isinstance(exc, DjangoValidationError):
        exc = _as_drf_validation_error(exc)
    elif isinstance(exc, DjangoPermissionDenied):
        return _envelope('Permission denied.', {}, CODE_PERMISSION,
                         status.HTTP_403_FORBIDDEN)
    elif isinstance(exc, Http404):
        # The wrong-branch case lands here: BranchScopedViewSet filtered the row
        # out, so get_object() raised 404 rather than 403 (CLAUDE.md §5).
        return _envelope('Not found.', {}, CODE_NOT_FOUND,
                         status.HTTP_404_NOT_FOUND)

    response = drf_exception_handler(exc, context)
    if response is not None:
        message, errors = _flatten(response.data)
        # An exception may name its own code (DRF's `default_code`, or one we
        # raise deliberately); fall back to the status code's meaning.
        declared = getattr(exc, 'default_code', None)
        code = (
            declared
            if declared and declared not in ('invalid', 'error')
            else _STATUS_CODES.get(response.status_code, CODE_ERROR)
        )
        return _envelope(message, errors, code, response.status_code)

    if isinstance(exc, IntegrityError):
        return _handle_integrity_error(exc, context)

    return None


def _as_drf_validation_error(exc):
    """A Django ValidationError in the shape DRF's handler understands.

    Model-level `full_clean()` and `Meta.constraints` raise Django's class, which
    DRF does not catch — without this it is a 500 for what is, to the caller, a
    bad field.
    """
    from rest_framework.exceptions import ValidationError as DRFValidationError

    if hasattr(exc, 'message_dict'):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError(exc.messages if hasattr(exc, 'messages') else str(exc))


def _handle_integrity_error(exc, context):
    """The net under endpoints that forgot their own check.

    Reaching here means a constraint fired that no serializer validated — for
    branch-scoped uniqueness, that is routine: the branch is stamped by the view
    and never on the serializer, so DRF builds no UniqueTogetherValidator for it
    and the duplicate goes all the way to Postgres.

    Logged at ERROR either way, because the log line is how the missing check
    gets found.
    """
    view = context.get('view')
    request = context.get('request')
    logger.error(
        'IntegrityError reached the API boundary: %s [view=%s path=%s]',
        exc,
        view.__class__.__name__ if view is not None else '?',
        getattr(request, 'path', '?'),
        exc_info=True,
    )

    sqlstate = _sqlstate(exc)

    if sqlstate == UNIQUE_VIOLATION_SQLSTATE:
        return _envelope(DUPLICATE_MESSAGE, {}, CODE_DUPLICATE,
                         status.HTTP_400_BAD_REQUEST)

    if sqlstate == FOREIGN_KEY_VIOLATION_SQLSTATE:
        # A PROTECT breach: something a fee, mark or attendance row points at is
        # being deleted. The user can act on this, so it is a 400 and not a 500.
        return _envelope(PROTECTED_MESSAGE, {}, CODE_PROTECTED,
                         status.HTTP_400_BAD_REQUEST)

    # A not-null or check-constraint breach is a bug in our code. Dressing it as
    # "you already have that" would tell the user something untrue and hide the
    # fault; returning None gives the honest 500 that gets it found.
    return None


class DuplicateError(APIException):
    """A 400 that keeps its shape when raised from a service.

    Deliberately not a DRF ValidationError: that class runs details through
    `as_serializer_error`, which wraps every value in a list — so the same error
    would reach the SPA as a string from one place and as a one-element list from
    another.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = CODE_DUPLICATE
    default_detail = DUPLICATE_MESSAGE
