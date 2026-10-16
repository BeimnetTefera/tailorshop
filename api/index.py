"""Vercel entry point: runs the app as a public demo (see DEMO_MODE in config/settings.py)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DEMO_MODE"] = "1"

from config.wsgi import application  # noqa: E402

app = application
