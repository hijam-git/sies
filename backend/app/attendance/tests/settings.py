"""Settings for running THIS app's tests before it is wired into the project.

`core/settings.py` still has `attendance` commented out of `_SIES_APPS`, and
`core/urls.py` still has its routes commented out — both are uncommented by the
phase that wires the app in, deliberately, so that the line which turns an app
on is a reviewable one-line change rather than a side effect of creating a
directory.

Until that line lands, `manage.py test attendance` cannot import a model,
because the app is not installed. This module is the bridge:

    python manage.py test attendance --settings=attendance.tests.settings

It changes nothing about the project. It imports the real settings and appends
one app, so every other setting — the database, the JWT block, the permission
resolver, `CELERY_TASK_ALWAYS_EAGER` under test — is the one production uses.

**Delete this file when `attendance` is added to `_SIES_APPS`.** A second
settings module that outlives its reason is how a suite quietly starts testing a
configuration nobody deploys.
"""

from core.settings import *  # noqa: F401,F403
from core.settings import INSTALLED_APPS as _INSTALLED_APPS

INSTALLED_APPS = [*_INSTALLED_APPS, 'attendance.apps.AttendanceConfig']

# Its own test database, and this is not tidiness. The shared `test_sies_dev` is
# built from the real INSTALLED_APPS, so `--keepdb` against it would never create
# the tables for the app added above — and dropping it to force that would take
# the whole team's `--keepdb` cache with it (CLAUDE.md §4a).
from core.settings import DATABASES  # noqa: E402

DATABASES['default'] = {**DATABASES['default'],
                        'TEST': {'NAME': 'test_sies_attendance'}}

# The API tests each apply `@override_settings(ROOT_URLCONF=...)` themselves, so
# this stays pointed at the real root — a test that forgot the override should
# fail with a 404 it can see, not silently pass against a different URL map.
