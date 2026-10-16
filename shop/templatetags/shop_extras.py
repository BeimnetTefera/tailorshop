from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from shop.models import plain_number

register = template.Library()


def format_etb(value):
    try:
        number = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    if number == number.to_integral_value():
        return f"{number:,.0f}"
    return f"{number:,.2f}"


@register.filter
def etb(value):
    """12500 -> '12,500'."""
    return format_etb(value)


@register.filter
def num(value):
    """Decimal('12.00') -> '12'."""
    return plain_number(value)


def _clock(dt):
    return f"{dt.hour % 12 or 12}:{dt:%M} {'AM' if dt.hour < 12 else 'PM'}"


@register.filter
def friendly(value):
    """'Today, 11:42 AM', 'Yesterday, 9:05 PM', 'Aug 21' style labels."""
    if not value:
        return ""
    today = timezone.localdate()
    if isinstance(value, datetime):
        local = timezone.localtime(value) if timezone.is_aware(value) else value
        day = local.date()
        if day == today:
            return f"Today, {_clock(local)}"
        if day == today - timedelta(days=1):
            return f"Yesterday, {_clock(local)}"
        return f"{local:%b} {local.day}, {_clock(local)}"
    if isinstance(value, date):
        if value == today:
            return "Today"
        if value == today - timedelta(days=1):
            return "Yesterday"
        return f"{value:%b} {value.day}"
    return value


# Simple stroke icons (24×24). Kept inline so pages work without an icon font.
ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z"/>',
    "orders": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>',
    "hanger": '<path d="M10 5.5a2 2 0 1 1 2 2v1.2"/><path d="M12 8.7 3.4 15.2A1 1 0 0 0 4 17h16a1 1 0 0 0 .6-1.8z"/>',
    "wallet": '<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M15 12.5h3"/><path d="M3 9h18"/>',
    "card": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "back": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "arrow-up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "arrow-down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
    "chev-left": '<path d="m15 6-6 6 6 6"/>',
    "chev-right": '<path d="m9 6 6 6-6 6"/>',
    "chev-down": '<path d="m6 9 6 6 6-6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    "filter": '<path d="M4 7h16M7 12h10M10 17h4"/>',
    "sort": '<path d="M8 20V4M4 8l4-4 4 4M16 4v16M12 16l4 4 4-4"/>',
    "bell": '<path d="M6 16v-5a6 6 0 1 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    "team": '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M16 7h5M16 11h5M17 15h4"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "badge": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "clipboard": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9zM9 11h6M9 15h4"/>',
    "logout": '<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10"/>',
    "alert": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
}


@register.simple_tag
def icon(name, size=22, label=""):
    paths = ICONS.get(name, "")
    aria = format_html('role="img" aria-label="{}"', label) if label else mark_safe('aria-hidden="true"')
    return format_html(
        '<svg class="ic" width="{0}" height="{0}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" {1}>{2}</svg>',
        size, aria, mark_safe(paths),
    )
