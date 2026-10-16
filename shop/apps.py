from django.apps import AppConfig


class ShopConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shop"
    verbose_name = "Tailor shop"

    def ready(self):
        # Django ships no Amharic locale; describe it so its language helpers know it.
        from django.conf.locale import LANG_INFO

        from . import pin  # noqa: F401  (connects the sign-in signal)

        LANG_INFO.setdefault("am", {"bidi": False, "code": "am", "name": "Amharic", "name_local": "አማርኛ"})
