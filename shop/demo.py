"""Demo helpers that must give the same result on every server instance.

On Vercel several instances run at once, each with its own demo database. Anything
random (password salts, copied files) would differ between them, so a visitor whose
next click lands on another instance would be signed out or miss a photo.
"""
from pathlib import Path

from django.contrib.auth.hashers import make_password

# Ready-made photos shipped with the app. A photo stored as "demo/<file>" is served
# straight from here, so it works on every instance without copying anything.
DEMO_PHOTOS = Path(__file__).resolve().parent / "demo_photos"
DEMO_PREFIX = "demo/"

# A fixed salt (long enough that Django won't re-hash it on login) gives every
# instance the same password hash, so the signed-in session stays valid everywhere.
_SALT = "TailorShopDemoSaltEthiopia2019"


def demo_password(raw):
    return make_password(raw, salt=_SALT)


def demo_photo(path):
    """The file for a 'demo/<name>' path, or None."""
    name = path[len(DEMO_PREFIX):]
    if "/" in name or "\\" in name or name in ("", ".", ".."):
        return None
    file = DEMO_PHOTOS / name
    return file if file.is_file() else None
