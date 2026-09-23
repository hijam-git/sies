"""Root URL configuration.

Traefik gives this process /api, /admin, /static and /media
(docker-compose.dev.yml); everything else is the SPA's. Nothing here may claim a
path outside those four prefixes, or it becomes unreachable behind the proxy.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from core.health import health
from core.media import serve_media

# Each app's router is included by the phase that writes it (docs/05 §8). The
# list is kept here, commented, rather than discovered: an include() naming a
# module that does not exist fails at import with a traceback that points at this
# file rather than at the missing app.
#
# All of them mount under /api/ with no version segment — the API and its one
# client deploy together, so a version prefix would be a number nobody ever
# changes (CLAUDE.md §5).
_MODULE_URLS = [
    path('api/', include('accounts.urls')),     # Phase 1 — auth, users, roles, activity
    path('api/', include('branches.urls')),     # Phase 1 — branches, streams, sessions
    path('api/', include('staff.urls')),        # Phase 2 — teachers, employees
    path('api/', include('academics.urls')),    # Phase 2 — classes, sections, subjects,
    #                                                       enrolment, periods, routine
    path('api/', include('students.urls')),     # Phase 2 — students, guardians, admissions
    path('api/', include('forms.urls')),  # Phase 3 — admission form templates
    path('api/', include('attendance.urls')),  # Phase 4 — register and period attendance
    path('api/', include('fees.urls')),  # Phase 5 — categories, fees, payments
    path('api/', include('finance.urls')),  # Phase 5 — income, expense
    path('api/', include('exams.urls')),  # Phase 6 — exams, schedules, marks
    path('api/', include('notifications.urls')),  # Phase 6 — SMS outbox, templates
    path('api/', include('conduct.urls')),  # Phase 6 — the observation register
    #
    # /api/me/ is a separate endpoint family, not a weakened staff permission
    # (docs/08 D4). It lives in accounts.urls and filters to request.user.
]

urlpatterns = [
    path('api/health/', health, name='health'),
    *_MODULE_URLS,
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    # Development. In production /static is whitenoise's (settings MIDDLEWARE)
    # and /media is either R2's presigned links or the route below.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
elif settings.MEDIA_ON_DISK:
    # Production with no R2. core/media.py says why this exists and why
    # documents/ is refused there rather than in this pattern.
    urlpatterns += [re_path(r'^media/(?P<path>.+)$', serve_media)]
