#!/bin/sh
# Apply migrations as the migrate user, load reference data, then serve as the
# least-privilege app user.
set -e
flask db upgrade
flask sync-top-packages || echo "warning: top-packages sync failed; typosquat checks will be empty"
exec gunicorn --workers 1 --threads 8 --bind 0.0.0.0:5000 --access-logfile - "app:create_app()"
