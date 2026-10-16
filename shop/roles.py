"""Who may do what: the owner sees everything, messengers run the day-to-day work."""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _


def is_owner(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return profile is not None and profile.role == profile.Role.OWNER


def owner_required(view):
    """Owner-only pages: finance, worker pay, prices, the team and messenger accounts."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_owner(request.user):
            messages.error(request, _("Only the owner can open that page."))
            return redirect("shop:dashboard")
        return view(request, *args, **kwargs)

    return wrapper
