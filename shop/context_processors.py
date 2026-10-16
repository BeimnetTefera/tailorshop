from django.conf import settings

from .roles import is_owner

# Maps URL names to the bottom-nav tab that should be highlighted.
_RULES = [
    ("dashboard", "home"),
    ("order_", "orders"),
    ("tracker", "orders"),
    ("readymade", "readymade"),
    ("freesize", "readymade"),
    ("sale", "readymade"),
    ("clothing", "stock"),
    ("style_", "stock"),
    ("material", "stock"),
    ("tibebe", "stock"),
    ("finance", "money"),
    ("income", "money"),
    ("worker_payments", "money"),
    ("task_", "money"),
    ("team", "home"),
    ("worker_", "home"),
    ("messenger_", "home"),
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
