#!/usr/bin/env python
"""Django's command-line utility. This is the real one.

It lives inside backend/app rather than beside it because backend/app IS /app
in both images (see Dockerfile.dev): compose bind-mounts ./backend/app over
/app, so a manage.py one directory up would be hidden the moment the dev stack
starts. backend/manage.py is a thin shim onto this file for running commands
from the host without Docker.
"""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
