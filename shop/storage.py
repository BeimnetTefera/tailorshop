from django.urls import reverse
from storages.backends.s3 import S3Storage


class PrivateS3Storage(S3Storage):
    """Supabase Storage (private bucket). Links point at the app, which checks the login."""

    def url(self, name, parameters=None, expire=None, http_method=None):
        return reverse("media_file", args=[name])
