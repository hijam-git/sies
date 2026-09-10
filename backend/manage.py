#!/usr/bin/env python
"""Host-side entry point — `python manage.py ...` from backend/.

The real utility is app/manage.py, because app/ is what becomes /app inside the
container (Dockerfile.dev explains why). This shim puts that directory on
sys.path and hands over, so there is exactly one copy of the settings-module
wiring and no chance of the two drifting.

Inside Docker nothing runs this file; compose's working directory is already
/app == backend/app.
"""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent / 'app'
sys.path.insert(0, str(APP_DIR))

if __name__ == '__main__':
    from manage import main  # noqa: E402  — app/manage.py, found via APP_DIR
    main()
