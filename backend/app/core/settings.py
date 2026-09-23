"""
Django settings for the SIES project.

Layout note: BASE_DIR is backend/app, which is /app inside both images. Every
path below (media, staticfiles, locale) is relative to it, so a path that works
in the dev container works in production and in a bare local run.

Nothing here is a secret with a working default. Anything unsafe to guess is read
from the environment and the process refuses to start without it, so a
misconfigured deploy fails loudly at boot rather than quietly running open.
(Adapted from awliaa/backend/app/core/settings.py.)
"""


import os
import re
import sys
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Only useful outside Docker — Compose injects the same variables via env_file,
# and load_dotenv never overwrites what is already set.
load_dotenv(BASE_DIR.parent.parent / '.env.development', override=False)


# ─────────────────────────────────────────────────────────────────────────────
# Environment-driven security settings
# ─────────────────────────────────────────────────────────────────────────────

DEBUG = os.getenv('DEBUG', 'False').strip().lower() in ('1', 'true', 'yes')

_secret_key = os.getenv('DJANGO_SECRET_KEY') or os.getenv('SECRET_KEY')
if not _secret_key:
    raise RuntimeError(
        'DJANGO_SECRET_KEY is not set. Add it to .env.development / '
        '.env.production before starting the server.'
    )
if not DEBUG and _secret_key.startswith('django-insecure-'):
    raise RuntimeError(
        'A django-insecure- key must not be used with DEBUG=False. '
        'Set DJANGO_SECRET_KEY to a strong random value.'
    )
SECRET_KEY = _secret_key

_allowed_hosts_env = os.getenv('ALLOWED_HOSTS', '').strip()
if _allowed_hosts_env:
    # Django spells a wildcard subdomain '.example.com', not '*.example.com'.
    # Accept the glob form too, because that is what people type.
    ALLOWED_HOSTS = [
        h[1:] if h.startswith('*.') else h
        for h in (part.strip() for part in _allowed_hosts_env.split(','))
        if h
    ]
elif DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    raise RuntimeError(
        'ALLOWED_HOSTS is not set and DEBUG=False. Set it to a comma-separated '
        'list of hostnames this server answers for.'
    )

# Traefik terminates TLS and forwards over plain HTTP on the internal network.
# Without this Django sees http:// on an already-secure request, which turns
# SECURE_SSL_REDIRECT into a redirect loop.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'

_csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '').strip()
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Applications
# ─────────────────────────────────────────────────────────────────────────────

# The domain apps of docs/01 §6, in dependency order. Each is uncommented by the
# phase that creates it (docs/05 §8). Listing them here now keeps that order
# visible, so nobody appends a new app to the bottom and quietly inverts a
# dependency the way docs/06 §2 forbids.
_SIES_APPS = [
    'accounts',     # Phase 1 — User, Role, ActivityLog
    'branches',     # Phase 1 — Branch, Stream, Session
    # Dependency order matters here: academics points at staff.Teacher, and
    # students points at academics.Enrolment. Appending a new app to the bottom
    # is how that order gets quietly inverted (docs/06 §2).
    'staff',        # Phase 2 — Teacher, Employee, TeacherQualification
    'academics',    # Phase 2 — AcademicClass, Section, Subject, Enrolment,
                    #           Period, ClassRoutine, SubjectAssignment
    'students',     # Phase 2 — Student, Guardian, Admission, Document
    'forms',        # Phase 2 — FormTemplate, Question, AdmissionAnswer
    'attendance',   # Phase 4 — DailyAttendance, ClassAttendance
    'fees',         # Phase 3 — FeeCategory, Fee, Payment
    'finance',      # Phase 3 — Income, Expense and their categories
    'exams',        # Phase 5 — Exam, ExamSchedule, Mark
    # SMS to guardians. docs/05 §5.4 had the whole outbox as V2; the result
    # message is V1 now because a result nobody is told about is a result on
    # a noticeboard. The other events §19 lists — fee due, absence, notices —
    # are still V2, and the table is shaped for them.
    'notifications',  # Phase 6 — NotificationTemplate, SmsMessage
    # What a student DOES, as against what exam marks say they know:
    # নামাজ, তিলাওয়াত, আদব. The institution writes its own items, so
    # nothing here knows what any of them mean (docs/02 §4.10).
    'conduct',      # Phase 6 — ReportTemplate, ReportItem, StudentReport
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',

    'core.apps.CoreConfig',
    *_SIES_APPS,
]

# The custom user model (docs/03 §1). Every abstract base in core/models.py
# points at settings.AUTH_USER_MODEL rather than at the class, so none of them
# had to change when this stopped being auth.User.
#
# This was conditional during Phase 0 — naming a model in an app that does not
# exist makes every management command fail at startup, including `check` and
# `migrate`, so the skeleton could not have tested itself. The accounts app now
# exists, so the condition is gone: a conditional auth user model is acceptable
# scaffolding and a liability in production, where "which user model is live?"
# must have exactly one answer.
AUTH_USER_MODEL = 'accounts.User'

# Where core.permissions looks up a user's effective permission set.
#
# core cannot import accounts — the dependency runs the other way (docs/06 §2) —
# so the resolver is named here and imported lazily. Without this line the
# fallback resolver in core applies, and it knows neither of the two rules that
# make the real one safe: an inactive user gets NO permissions rather than their
# role preset (a dismissed employee must not keep working access), and a saved
# permission string that is no longer in the catalogue is dropped rather than
# honoured. Both are worklog F1.
SIES_PERMISSION_RESOLVER = 'accounts.permissions.permission_resolver'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Straight after SecurityMiddleware, as whitenoise requires: a /static hit
    # is answered here and never reaches sessions, auth or branch scoping.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Resolves request.branch (docs/01 §5.2, docs/02 §3). Must come after
    # AuthenticationMiddleware; core/middleware.py explains why the value is lazy.
    'core.middleware.BranchScopeMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'


# ─────────────────────────────────────────────────────────────────────────────
# Database
#
# Postgres only — there is no SQLite fallback. Branch scoping leans on real
# constraints and the fee tables will lean on SELECT … FOR UPDATE (CLAUDE.md
# §4.4); a fallback engine that behaves differently under concurrency would only
# let a bug pass locally and appear in production.
#
# The defaults match docker-compose.dev.yml so `dev.sh up` works with no .env at
# all; production supplies every one of them.
# ─────────────────────────────────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'sies_dev'),
        'USER': os.getenv('DB_USER', 'sies'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'sies_dev_password'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        # Persistent connections: with Postgres on the same box, reconnecting per
        # request is measurable overhead for nothing.
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '600')),
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ─────────────────────────────────────────────────────────────────────────────
# Passwords
# ─────────────────────────────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    # NumericPasswordValidator is deliberately absent: staff accounts are created
    # by an admin with a numeric initial password and must_change_password set
    # (docs/03 §1), and this validator would reject that at creation time.
]


# ─────────────────────────────────────────────────────────────────────────────
# Internationalisation
#
# Bangla is the default and English is the toggle (docs/08 §7, assumption 1) —
# the reverse of most Django projects, and the reason LANGUAGE_CODE is 'bn'
# rather than English with a Bangla translation bolted on afterwards.
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = 'bn'

LANGUAGES = [
    ('bn', 'বাংলা'),
    ('en', 'English'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

TIME_ZONE = 'Asia/Dhaka'

USE_I18N = True
USE_TZ = True


# ─────────────────────────────────────────────────────────────────────────────
# Static and media
# ─────────────────────────────────────────────────────────────────────────────

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
# The fallback when no object store is configured: a named volume in both
# compose files. Still the right answer for a single-server install.
MEDIA_ROOT = BASE_DIR / 'media'

# ─────────────────────────────────────────────────────────────────────────────
# Cloudflare R2 — where uploaded files live (docs/01 §8, core/storage.py)
# ─────────────────────────────────────────────────────────────────────────────
#
# **The bucket must be PRIVATE — no r2.dev domain, no custom domain.** It holds
# students' birth certificates and an institution's fee vouchers, not product
# photos. `core.storage.R2Storage` hands out presigned links that expire, and
# `Document.file` is still streamed through the authenticated endpoint, so
# there is no permanent URL to leak either way — but a bucket served publicly
# would make both of those precautions decoration.
#
# Not configured is not an error: the disk below keeps working exactly as it
# does today, which is what dev, CI and a one-server deployment run on.
R2_ACCOUNT_ID = os.getenv('R2_ACCOUNT_ID', '')
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY', '')
R2_BUCKET = os.getenv('R2_BUCKET', '')
# Derived from the account id; set only for a non-standard endpoint.
R2_ENDPOINT_URL = os.getenv('R2_ENDPOINT_URL', '')
# How long a presigned link lives. Five minutes: long enough for a page to load
# a photo, short enough that a forwarded URL is already dead.
R2_PRESIGN_TTL = int(os.getenv('R2_PRESIGN_TTL', '300'))

# Offsite database backups go to a SEPARATE bucket, and the separation is the
# point: a dump in the media bucket is every student, guardian phone number and
# fee record one guessed key away. `backup_to_r2` refuses to run when this is
# empty or equal to R2_BUCKET.
R2_BACKUP_BUCKET = os.getenv('R2_BACKUP_BUCKET', '')

# Which server a dump came from — it goes in the FILENAME, because one bucket
# may hold dumps from production, staging and a migration box at once.
SIES_SERVER_NAME = re.sub(
    r'[^a-zA-Z0-9-]+', '-',
    os.getenv('THIS_SERVER_NAME', '') or os.getenv('DOMAIN', '') or 'server',
).strip('-')[:32] or 'server'

# Django 5's storage registry. One switch decides where every FileField in the
# project writes, so no model, migration or call site knows the difference.
STORAGES = {
    'default': (
        {'BACKEND': 'core.storage.R2Storage'}
        if all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET])
        else {'BACKEND': 'django.core.files.storage.FileSystemStorage'}
    ),
    # Compressed, not Manifest: the manifest variant raises on any {% static %}
    # name missing from the manifest whenever DEBUG is off — which includes the
    # test runner — so a test rendering the admin would need collectstatic first.
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# True when uploads live on this server's disk rather than in R2. core/urls.py
# reads it to decide whether Django has to serve /media itself.
MEDIA_ON_DISK = STORAGES['default']['BACKEND'].endswith('FileSystemStorage')

# A scanned admission document or a photo from a phone camera routinely exceeds
# Django's 2.5 MB default, at which point the upload spools to a temp file. This
# is the ceiling that actually refuses one.
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# CORS
#
# Behind Traefik the SPA and the API share an origin, so this list is normally
# empty and CORS never comes into it. It exists for a Vite dev server run outside
# the compose stack.
# ─────────────────────────────────────────────────────────────────────────────

_cors_origins_env = os.getenv('CORS_ALLOWED_ORIGINS', '').strip()
if _cors_origins_env:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_env.split(',') if o.strip()]
else:
    CORS_ALLOW_ALL_ORIGINS = DEBUG

CORS_ALLOW_CREDENTIALS = True


# ─────────────────────────────────────────────────────────────────────────────
# Django REST Framework
#
# No DEFAULT_THROTTLE_* and nothing cache-backed: CLAUDE.md §1 rules out rate
# limiting and a caching layer for this project. awliaa's core/throttles.py is
# not to be ported.
# ─────────────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        # Session auth serves the browsable API and the Django admin only. The
        # SPA authenticates with JWT and nothing else.
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Authenticated by default, so a viewset that forgets its permission class is
    # still closed. Public endpoints opt out one at a time, visibly.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # One error shape for the entire API (CLAUDE.md §5). See
    # core/exception_handlers.py.
    'EXCEPTION_HANDLER': 'core.exception_handlers.api_exception_handler',
    'DEFAULT_RENDERER_CLASSES': (
        ['rest_framework.renderers.JSONRenderer',
         'rest_framework.renderers.BrowsableAPIRenderer']
        if DEBUG else
        ['rest_framework.renderers.JSONRenderer']
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    # With rotation, every refresh issues a fresh long-lived token, so someone
    # working daily is never logged out mid-task while an abandoned session still
    # expires. An accountant losing their session halfway through a day of fee
    # collection is the failure this is tuned against.
    'REFRESH_TOKEN_LIFETIME': timedelta(days=90),
    'ROTATE_REFRESH_TOKENS': True,
    # Needs rest_framework_simplejwt.token_blacklist in INSTALLED_APPS: the old
    # refresh token is revoked at rotation, so a stolen one works only until the
    # real user next refreshes.
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# ─────────────────────────────────────────────────────────────────────────────
# Celery
#
# Redis is the broker and the result backend and nothing else — CLAUDE.md §1
# forbids using it as a cache. The URLs default to the compose service names.
# ─────────────────────────────────────────────────────────────────────────────

REDIS_URL = os.getenv('REDIS_URL', 'redis://sies-redis:6379/0')

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://sies-redis:6379/2')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True

# Celery's default of 4 means a worker child holds up to four tasks it is not
# running, acknowledged the moment they were taken. A worker that dies takes them
# with it — not failed, not retried, simply never done. For a queue that raises a
# month of fees this is not a close call: 1 costs a little throughput on short
# tasks and loses nothing across a restart or a deploy.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# acks_late is set PER TASK, never globally here. It turns at-most-once into
# at-least-once: a task interrupted mid-run goes back on the queue and RUNS
# AGAIN. That is correct for the idempotent sweeps — fee generation is keyed on
# (student, category, period) with a unique constraint (docs/01 §4) — and wrong
# for anything that mints a receipt number or sends an SMS. Each task decides for
# itself, next to the code that makes the claim true.

# Two queues, so one long export cannot starve fee generation (docs/01 §4).
# docker-compose.dev.yml starts the worker with -Q default,slow, so
# CELERY_TASK_DEFAULT_QUEUE must be 'default' and not Celery's own 'celery' —
# a task routed to a queue nobody consumes waits forever without erroring.
# Routes match on app prefix rather than task name: a second export task in the
# same module then lands on the right queue without anyone adding a line.
CELERY_TASK_ROUTES = {
    # Long, resumable, someone-is-waiting-for-a-download work: PDF marksheets and
    # certificates, CSV ledgers, bulk SMS fan-out.
    'core.tasks.export_*': {'queue': 'slow'},
    'exams.tasks.publish_results': {'queue': 'slow'},
    # Results day queues one task per guardian — four hundred of them in one
    # press. On `default` they would sit in front of whatever a person is
    # actually waiting for; on `slow` they run beside it. The comment above
    # always said bulk SMS belonged here; the route did not exist.
    'notifications.deliver_sms': {'queue': 'slow'},
}
CELERY_TASK_DEFAULT_QUEUE = 'default'

CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60

# Beat's schedule, empty until Phase 5. Every job docs/01 §4 lists — monthly fee
# generation, nightly fines, activity-log pruning, backups — belongs to an app
# that does not exist yet, and an entry naming a task Celery cannot import makes
# beat crash-loop rather than skip it. Each entry is added by the phase that
# writes its task, so the schedule and the code land together.
CELERY_BEAT_SCHEDULE = {
    # The clock behind the "smart" claim in docs/00 §2. Nobody clicks any of
    # these, and an institution that never opens the Fees screen still has its
    # month raised and its fines accrued.
    #
    # Entries name a task by its registered string rather than importing it: an
    # entry pointing at an unimportable task makes beat crash-loop at startup
    # instead of skipping it, so a typo here takes the whole scheduler down.

    # Decision 2 of the smart list. Safe to fire twice — the invoice's unique key
    # on (branch, student, category, period, session) is what makes a retried
    # run write nothing rather than double-charging a guardian.
    'fees.generate-monthly': {
        'task': 'fees.generate_monthly_fees',
        'schedule': crontab(minute=15, hour=0, day_of_month='1'),
        'options': {'queue': 'default'},
    },

    # Decision 3. Depends on the passage of time rather than on a user action,
    # which is precisely why it cannot live in a request.
    'fees.accrue-fines': {
        'task': 'fees.accrue_fines',
        'schedule': crontab(minute=30, hour=0),
        'options': {'queue': 'default'},
    },

    # A branch whose fine_rule has per_day = 0 never enters the fine job, so its
    # invoices would sit at `unpaid` past their due date forever and the Dues
    # screen would quietly under-report. This moves them to `overdue` on time
    # regardless of whether a fine applies.
    'fees.mark-overdue': {
        'task': 'fees.mark_overdue',
        'schedule': crontab(minute=40, hour=0),
        'options': {'queue': 'default'},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Logging
#
# stdout only. Docker collects it; a log file inside a container is a log file
# nobody reads on a disk nobody watches.
# ─────────────────────────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django.db.backends': {
            # SQL at DEBUG is a wall of text that buries everything else, so it
            # is opt-in per session rather than something to live with.
            'level': 'DEBUG' if os.getenv('LOG_SQL') == '1' else 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# SMS — docs/02 §4.9. The gateway is the platform's; the sender is the branch's.
# ─────────────────────────────────────────────────────────────────────────────

# **`console` is the default on purpose.** It writes every message to the log
# and sends nothing, so a fresh install, CI, and a `seed_demo` database full of
# invented numbers cannot text a stranger or spend a taka. Production sets
# SMS_PROVIDER=bulksmsbd and supplies the key below; nothing else changes.
SMS_PROVIDER = os.getenv('SMS_PROVIDER', 'console')

# One gateway account for the platform. The name on the handset is per
# institution — `Branch.sms_sender_id` — because a madrasah and a college
# sharing this deployment must not appear to each other's guardians as the same
# sender. This is the fallback for a branch that has not registered one.
SMS_SENDER_ID = os.getenv('SMS_SENDER_ID', '')

BULKSMSBD_API_KEY = os.getenv('BULKSMSBD_API_KEY', '')
# HTTPS: the API key is a query parameter on every request, so over plain HTTP
# it crosses every network between here and the gateway in the clear.
BULKSMSBD_BASE_URL = os.getenv('BULKSMSBD_BASE_URL', 'https://bulksmsbd.net/api')


# ─────────────────────────────────────────────────────────────────────────────
# Test configuration
# ─────────────────────────────────────────────────────────────────────────────

# manage.py sits at the root of the app tree, so unittest's discovery from the
# cwd finds nothing without help. See core/test_runner.py.
TEST_RUNNER = 'core.test_runner.LocalAppsDiscoverRunner'

TESTING = 'test' in sys.argv or os.path.basename(sys.argv[0] or '') == 'pytest'
if TESTING:
    # Tasks run inline, against the test database. Without this, a test that
    # queues fee generation hands it to the dev worker — which is connected to
    # the REAL database and would act on rows the test never created. awliaa hit
    # exactly this with order emails; here it would be someone's money.
    CELERY_TASK_ALWAYS_EAGER = True
    # A broken background job must not fail the test of the thing that queued it.
    # The task gets its own test.
    CELERY_TASK_EAGER_PROPAGATES = False

    # Password hashing is the largest single cost in a suite that creates users,
    # and no test cares which algorithm proved the password.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

    # Uploads go to the disk under test even when the environment carries R2
    # credentials, as .env.development may: otherwise every test that saves a
    # photo writes a real object to the bucket, over the network, and leaves it
    # there. test_storage exercises R2Storage directly with a stubbed client.
    STORAGES = {**STORAGES, 'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}}
    MEDIA_ON_DISK = True
