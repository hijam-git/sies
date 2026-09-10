"""Test runner that defaults to this project's own apps.

manage.py sits at the root of the app tree, so unittest's discovery from the cwd
finds the apps but also walks site-packages under some layouts. When no labels
are given, fall back to every local app.

Which apps those are is worked out from INSTALLED_APPS by PATH rather than from a
hand-written list. awliaa kept a list here and it stopped being updated — four
apps had tests that a bare `manage.py test` silently skipped, and a suite that
quietly omits an app is worse than one that fails, because it reports OK. Locating
by path means a third-party package (never inside our source tree) is excluded
automatically and a new app of ours is picked up the moment it is installed. That
matters more here than it did there: this project adds an app per phase.
"""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test.runner import DiscoverRunner


def local_app_labels():
    """Apps whose code lives in this repo, in INSTALLED_APPS order."""
    root = Path(settings.BASE_DIR).resolve()
    labels = []
    for config in apps.get_app_configs():
        try:
            path = Path(config.path).resolve()
        except (OSError, ValueError):
            continue
        if path == root or root in path.parents:
            labels.append(config.label)
    return labels


class LocalAppsDiscoverRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, **kwargs):
        if not test_labels:
            test_labels = local_app_labels()
        return super().build_suite(test_labels, **kwargs)
