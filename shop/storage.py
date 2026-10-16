import mimetypes
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.urls import reverse
from storages.backends.s3 import S3Storage

# Phone photos are several megabytes; this is plenty for an order or product photo.
MAX_SIDE = 1600


class PrivateS3Storage(S3Storage):
    """Supabase Storage (private bucket). Links point at the app, which checks the login."""

    def url(self, name, parameters=None, expire=None, http_method=None):
        return reverse("media_file", args=[name])


def shrink_image(data, name):
    """Turn a phone photo the right way up and make it at most MAX_SIDE pixels wide or tall.

    Anything that isn't an image Pillow can read is kept as it is.
    """
    from PIL import Image, ImageOps

    try:
        image = Image.open(BytesIO(data))
        fmt = image.format
        image = ImageOps.exif_transpose(image)
    except Exception:
        return data
    if fmt not in ("JPEG", "PNG", "WEBP"):
        return data
    too_big = max(image.size) > MAX_SIDE
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = BytesIO()
    if fmt == "JPEG":
        image.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
    else:
        image.save(out, fmt, optimize=True)
    result = out.getvalue()
    # A small photo that came out bigger after re-saving is kept as it was.
    return result if too_big or len(result) < len(data) else data


class DatabaseStorage(Storage):
    """Uploaded photos kept in the database (shop.StoredFile).

    Used on Vercel when there's a database but no file storage: every server instance
    reads the same database, so a photo posted on one is there on all of them.
    """

    def _model(self):
        from .models import StoredFile

        return StoredFile

    def _open(self, name, mode="rb"):
        row = self._model().objects.filter(name=name).only("data").first()
        if row is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(row.data), name=name)

    def _save(self, name, content):
        if hasattr(content, "seek"):
            content.seek(0)
        data = shrink_image(content.read(), name)
        self._model().objects.create(name=name, data=data, size=len(data),
                                     content_type=mimetypes.guess_type(name)[0] or "")
        return name

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def size(self, name):
        row = self._model().objects.filter(name=name).only("size").first()
        if row is None:
            raise FileNotFoundError(name)
        return row.size

    def url(self, name):
        return reverse("media_file", args=[name])
