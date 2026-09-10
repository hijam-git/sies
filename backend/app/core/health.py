"""Liveness probe for Traefik, Docker healthchecks and scripts/health_check.sh."""

from django.http import JsonResponse


def health(_request):
    """Proves the process is serving, and nothing more.

    Deliberately touches no database, no Redis and no branch scoping. A probe
    that checks its dependencies reports the whole stack down when one of them
    is, which makes the orchestrator restart a healthy container and turns a
    Postgres hiccup into an outage. scripts/health_check.sh checks Postgres,
    Redis and the worker separately, where a failure can be read for what it is.
    """
    return JsonResponse({'status': 'ok'})
