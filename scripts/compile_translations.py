"""Build locale/*/LC_MESSAGES/django.mo from the .po files.

Django's `compilemessages` needs GNU gettext, which Windows doesn't have, so this uses
polib instead (`pip install polib`). Run it after editing a .po file and commit both.
"""
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parent.parent

for po_path in sorted((ROOT / "locale").glob("*/LC_MESSAGES/*.po")):
    po = polib.pofile(str(po_path))
    po.save_as_mofile(str(po_path.with_suffix(".mo")))
    done = len(po.translated_entries())
    print(f"{po_path.relative_to(ROOT)}: {done} of {len([e for e in po if not e.obsolete])} translated")
