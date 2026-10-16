"""Ethiopian calendar: 12 months of 30 days, then Pagume with 5 days (6 in a leap year).

The year starts on Meskerem 1 (September 11, or September 12 before a Gregorian leap
year). Conversion goes through day numbers (date.toordinal), following Dershowitz &
Reingold, "Calendrical Calculations".
"""
from datetime import date
from typing import NamedTuple

from django.utils import translation

# Meskerem 1 of year 1 (Amete Mihret) as a proleptic Gregorian day number.
EPOCH = 2796

MONTHS_AM = ["መስከረም", "ጥቅምት", "ኅዳር", "ታኅሣሥ", "ጥር", "የካቲት", "መጋቢት",
             "ሚያዝያ", "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ"]
MONTHS_EN = ["Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit", "Megabit",
             "Miyazya", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume"]
# Monday first, matching date.weekday().
WEEKDAYS_AM = ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "ዓርብ", "ቅዳሜ", "እሑድ"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class EthDate(NamedTuple):
    year: int
    month: int
    day: int


def is_leap(year):
    return year % 4 == 3


def month_length(year, month):
    if month < 13:
        return 30
    return 6 if is_leap(year) else 5


def _ordinal(year, month, day):
    return EPOCH - 1 + 365 * (year - 1) + year // 4 + 30 * (month - 1) + day


def to_gregorian(year, month, day):
    if not (1 <= month <= 13 and 1 <= day <= month_length(year, month)):
        raise ValueError(f"{year}-{month}-{day} is not a day in the Ethiopian calendar")
    return date.fromordinal(_ordinal(year, month, day))


def from_gregorian(value):
    n = value.toordinal()
    year = (4 * (n - EPOCH) + 1463) // 1461
    month = (n - _ordinal(year, 1, 1)) // 30 + 1
    day = n - _ordinal(year, month, 1) + 1
    return EthDate(year, month, day)


def month_bounds(year, month):
    """First and last Gregorian dates of an Ethiopian month."""
    return to_gregorian(year, month, 1), to_gregorian(year, month, month_length(year, month))


def add_months(year, month, delta):
    index = year * 13 + (month - 1) + delta
    return index // 13, index % 13 + 1


def _amharic():
    return (translation.get_language() or "").startswith("am")


def month_name(month):
    return (MONTHS_AM if _amharic() else MONTHS_EN)[month - 1]


def weekday_name(value):
    return (WEEKDAYS_AM if _amharic() else WEEKDAYS_EN)[value.weekday()]


def format_date(value, style="long"):
    """long: 'Tikimt 6, 2019' · short: 'Tikimt 6' · month: 'Tikimt 2019' · full: with weekday and era."""
    e = from_gregorian(value)
    name = month_name(e.month)
    if style == "short":
        return f"{name} {e.day}"
    if style == "month":
        return f"{name} {e.year}"
    if style == "full":
        if _amharic():
            return f"{weekday_name(value)}፣ {name} {e.day} ቀን {e.year} ዓ.ም."
        return f"{weekday_name(value)}, {name} {e.day}, {e.year} E.C."
    return f"{name} {e.day}, {e.year}"


def format_range(start, end):
    """'Tikimt 1–7, 2019', 'Tikimt 29 – Hidar 5, 2019' or full dates when the year changes."""
    s, e = from_gregorian(start), from_gregorian(end)
    if s.year != e.year:
        return f"{format_date(start)} – {format_date(end)}"
    if s.month != e.month:
        return f"{format_date(start, 'short')} – {format_date(end, 'short')}, {e.year}"
    return f"{month_name(s.month)} {s.day}–{e.day}, {e.year}"


def today():
    from django.utils import timezone

    return from_gregorian(timezone.localdate())
