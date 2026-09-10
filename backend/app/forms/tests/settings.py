"""Settings for running this module's tests before its phase wires the app in.

`core/settings.py` still has `forms` commented out of `_SIES_APPS` — the phase
that owns that file uncomments it, and this module must not edit it (docs/05 §8:
one phase at a time, and settings.py is where the app *order* is deliberately
kept visible, so appending to it from a module is exactly the mistake the
comment there warns about).

Until then the tests run as:

    scripts/dev.sh test forms --settings=forms.tests.settings

Nothing else differs from the real settings, on purpose: a test settings module
that changes behaviour ends up testing the settings module rather than the code.
"""

from pathlib import Path

from core.settings import *  # noqa: F401,F403
from core.settings import INSTALLED_APPS as _INSTALLED_APPS

_BASE = Path(__file__).resolve().parent.parent.parent

# Apps that exist on disk but are still commented out of `_SIES_APPS`. `forms`
# is this module's own; the others are here because `branches.seeding` — which
# every fixture reaches through `create_branch()` — imports them, so leaving one
# out makes this module's tests unrunnable for a reason that has nothing to do
# with forms. Discovered rather than hard-listed, so it needs no edit as the
# remaining phases land, and it disappears entirely once settings.py catches up.
_PENDING = ['fees', 'finance', 'attendance', 'exams', 'forms']

INSTALLED_APPS = [
    *_INSTALLED_APPS,
    *[app for app in _PENDING
      if app not in _INSTALLED_APPS and (_BASE / app / 'apps.py').exists()],
]
