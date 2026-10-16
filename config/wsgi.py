import os

import django
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

if settings.ON_VERCEL:
    # Apply new migrations on start-up; a no-op once the database is up to date.
    call_command("migrate", interactive=False, verbosity=0)
    if settings.DEMO_MODE:
        # Each demo instance starts with an empty /tmp, so load the demo data.
        call_command("seed_demo", verbosity=0)

application = get_wsgi_application()
