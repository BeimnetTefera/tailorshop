import os

import django
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
if os.environ.get("VERCEL") == "1":
    os.environ.setdefault("DEMO_MODE", "1")

if os.environ.get("DEMO_MODE") == "1":
    # Each demo instance starts with an empty /tmp, so build the database and load demo data.
    django.setup()
    call_command("migrate", interactive=False, verbosity=0)
    call_command("seed_demo", verbosity=0)

application = get_wsgi_application()
