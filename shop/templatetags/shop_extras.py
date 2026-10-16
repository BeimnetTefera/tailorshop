from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone, translation
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from shop import ethiopian
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
def birr(value):
    """12500 -> '12,500 ብር' (Amharic) or '12,500 ETB' (English)."""
    return f"{format_etb(value)} {gettext('ETB')}"


@register.filter
def num(value):
    """Decimal('12.00') -> '12'."""
    return plain_number(value)


def _as_date(value):
    if isinstance(value, datetime):
        return (timezone.localtime(value) if timezone.is_aware(value) else value).date()
    return value


@register.filter
def ethdate(value, style="long"):
    """Gregorian date -> Ethiopian: long 'Tikimt 6, 2019', short 'Tikimt 6', month, full."""
    if not value:
        return ""
    return ethiopian.format_date(_as_date(value), style)


@register.filter
def ethrange(start, end):
    return ethiopian.format_range(_as_date(start), _as_date(end))


def clock(dt):
    hour = f"{dt.hour % 12 or 12}:{dt:%M}"
    if (translation.get_language() or "").startswith("am"):
        return f"{hour} {'ጥዋት' if dt.hour < 12 else 'ከሰዓት'}"
    return f"{hour} {'AM' if dt.hour < 12 else 'PM'}"


@register.filter
def friendly(value):
    """'Today, 11:42 AM', 'Yesterday, 9:05 PM', 'Tikimt 3' style labels."""
    if not value:
        return ""
    today = timezone.localdate()
    if isinstance(value, datetime):
        local = timezone.localtime(value) if timezone.is_aware(value) else value
        day = local.date()
        if day == today:
            return gettext("Today, %(time)s") % {"time": clock(local)}
        if day == today - timedelta(days=1):
            return gettext("Yesterday, %(time)s") % {"time": clock(local)}
        return f"{ethiopian.format_date(day, 'short')}, {clock(local)}"
    if isinstance(value, date):
        if value == today:
            return gettext("Today")
        if value == today - timedelta(days=1):
            return gettext("Yesterday")
        return ethiopian.format_date(value, "short")
    return value


@register.simple_tag
def other_language():
    """The language the switch button changes to."""
    return "en" if (translation.get_language() or "").startswith("am") else "am"


# Simple stroke icons (24×24). Kept inline so pages work without an icon font.
ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    "orders": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9zM9 12h6M9 16h4"/>',
    "hanger": '<path d="M12 7a2 2 0 1 1 2-2M12 7v2l9 6v2H3v-2l9-6"/>',
    "box": '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5zM3 7.5 12 12l9-4.5M12 12v9"/>',
    "wallet": '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M16 13h2M3 10h18"/>',
    "card": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/>',
    "receipt": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "back": '<path d="m15 5-7 7 7 7"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "arrow-up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "arrow-down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
    "chev-left": '<path d="m15 6-6 6 6 6"/>',
    "chev-right": '<path d="m9 6 6 6-6 6"/>',
    "chev-down": '<path d="m6 9 6 6 6-6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    "filter": '<path d="M4 7h16M7 12h10M10 17h4"/>',
    "sort": '<path d="M8 20V4M4 8l4-4 4 4M16 4v16M12 16l4 4 4-4"/>',
    "bell": '<path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9zM10 20a2 2 0 0 0 4 0"/>',
    "team": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    "send": '<path d="M4 12 20 4l-5 16-3-7z"/>',
    "check": '<path d="m5 12 4.5 4.5L19 7"/>',
    "badge": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "clipboard": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9zM9 11h6M9 15h4"/>',
    "logout": '<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10"/>',
    "alert": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    "more": '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
}


@register.simple_tag
def icon(name, size=22, label=""):
    paths = ICONS.get(name, "")
    aria = format_html('role="img" aria-label="{}"', label) if label else mark_safe('aria-hidden="true"')
    return format_html(
        '<svg class="ic" width="{0}" height="{0}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" {1}>{2}</svg>',
        size, aria, mark_safe(paths),
    )
