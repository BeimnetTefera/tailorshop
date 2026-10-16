# Maps URL names to the bottom-nav tab that should be highlighted.
_RULES = [
    ("dashboard", "home"),
    ("order_", "orders"),
    ("tracker", "orders"),
    ("clothing", "inventory"),
    ("style_", "inventory"),
    ("material", "inventory"),
    ("tibebe", "inventory"),
    ("freesize", "inventory"),
    ("sale", "finance"),
    ("finance", "finance"),
    ("income", "finance"),
    ("worker_payments", "payments"),
    ("task_", "payments"),
    ("team", "home"),
    ("worker_", "home"),
]


def demo(request):
    from django.conf import settings
    return {"demo_mode": settings.DEMO_MODE}


def navigation(request):
    match = getattr(request, "resolver_match", None)
    name = (match.url_name if match else "") or ""
    for prefix, section in _RULES:
        if name.startswith(prefix):
            return {"nav_section": section}
    return {"nav_section": ""}
