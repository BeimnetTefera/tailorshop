import os

import django
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection, transaction  # noqa: E402

# Any number makes a lock name; this one is just the app's own.
_SETUP_LOCK = 20191006


def _prepare_database():
    """Apply new migrations and, for a demo, load the demo data (skipped if it's there)."""
    call_command("migrate", interactive=False, verbosity=0)
    if settings.DEMO_MODE or settings.DEMO_DATA:
        call_command("seed_demo", verbosity=0)


if settings.ON_VERCEL:
    if connection.vendor == "postgresql":
        # Several instances can start at once against the same database: the first takes
        # the lock and sets up, the others wait for it and then find nothing left to do.
        # A transaction-level lock also works through connection poolers.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_SETUP_LOCK])
            _prepare_database()
    else:
        _prepare_database()

application = get_wsgi_application()
