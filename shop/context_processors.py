from django.conf import settings

from .roles import is_owner

# Maps URL names to the bottom-nav tab that should be highlighted.
_RULES = [
    ("dashboard", "home"),
    ("order_", "orders"),
    ("tracker", "orders"),
    ("readymade", "collection"),
    ("freesize", "collection"),
    ("sale", "collection"),
    ("clothing", "collection"),
    ("style_", "collection"),
    ("material", "stock"),
    ("finance", "money"),
    ("income", "money"),
    ("worker_payments", "money"),
    ("task_", "money"),
    ("manage", "team"),
    ("team", "team"),
    ("worker_", "team"),
    ("messenger_", "team"),
    ("account", "home"),
]


def demo(request):
    return {"demo_mode": settings.DEMO_MODE}


def roles(request):
    return {"is_owner": is_owner(request.user)}


def navigation(request):
    match = getattr(request, "resolver_match", None)
    name = (match.url_name if match else "") or ""
    for prefix, section in _RULES:
        if name.startswith(prefix):
            return {"nav_section": section}
    return {"nav_section": ""}
