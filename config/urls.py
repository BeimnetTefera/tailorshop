from django.contrib import admin
from django.urls import include, path

from shop.views import media_file

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("media/<path:path>", media_file, name="media_file"),
    path("", include("shop.urls")),
]
