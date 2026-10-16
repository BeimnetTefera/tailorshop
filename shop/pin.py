"""PIN confirmation for changes that are hard to undo, and "sign out all other devices".

The flow: a protected form asks for the PIN in a sheet, the page checks it with
`verify` and receives a short-lived signed token, and the form is submitted with
that token. Views decorated with `pin_required` refuse a POST without a valid
token, so nothing protected is saved by accident.
"""
import re
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.signals import user_logged_in
from django.core import signing
from django.dispatch import receiver
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

PIN_RE = re.compile(r"^\d{4,6}$")
MAX_TRIES = 5
LOCK_MINUTES = 5
TOKEN_SECONDS = 120  # the token only has to survive the trip from the PIN sheet to the form submit
_SIGNER = signing.TimestampSigner(salt="shop.pin")


def profile_for(user):
    """The user's StaffProfile, created on the spot for an owner made with createsuperuser."""
    from .models import StaffProfile

    profile = getattr(user, "profile", None)
    if profile is None:
        role = StaffProfile.Role.OWNER if user.is_superuser else StaffProfile.Role.MESSENGER
        profile, _created = StaffProfile.objects.get_or_create(user=user, defaults={"role": role})
    return profile


def has_pin(user):
    profile = getattr(user, "profile", None)
    return bool(profile and profile.pin_hash)


def _token_for(user):
    return _SIGNER.sign(str(user.pk))


def token_ok(request):
    token = request.POST.get("pin_token", "")
    try:
        return _SIGNER.unsign(token, max_age=TOKEN_SECONDS) == str(request.user.pk)
    except signing.BadSignature:
        return False


def _back(request):
    for target in (request.POST.get("next"), request.META.get("HTTP_REFERER")):
        if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
            return target
    return "shop:dashboard"


def pin_required(view):
    """POSTs to this view must carry a fresh PIN token (see verify)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method == "POST" and not token_ok(request):
            messages.error(request, _("Nothing was changed. Enter your PIN to confirm changes like this."))
            return redirect(_back(request))
        return view(request, *args, **kwargs)

    wrapper.pin_protected = True
    return wrapper


def _locked_seconds(profile):
    if profile.pin_locked_until and profile.pin_locked_until > timezone.now():
        return int((profile.pin_locked_until - timezone.now()).total_seconds()) + 1
    return 0


@require_POST
def verify(request):
    """Check a PIN; reply with a token the protected form sends along."""
    profile = profile_for(request.user)
    if not profile.pin_hash:
        return JsonResponse({"ok": False, "needs_pin": True, "error": _("Create your PIN first.")}, status=400)
    locked = _locked_seconds(profile)
    if locked:
        return JsonResponse({"ok": False, "error": _("Too many wrong tries. Wait %(n)s minutes and try again.")
                             % {"n": (locked + 59) // 60}}, status=429)
    if check_password(request.POST.get("pin", ""), profile.pin_hash):
        if profile.pin_failures:
            profile.pin_failures = 0
            profile.save(update_fields=["pin_failures"])
        return JsonResponse({"ok": True, "token": _token_for(request.user)})
    profile.pin_failures += 1
    fields = ["pin_failures"]
    if profile.pin_failures >= MAX_TRIES:
        profile.pin_failures = 0
        profile.pin_locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
        fields.append("pin_locked_until")
        profile.save(update_fields=fields)
        return JsonResponse({"ok": False, "error": _("Too many wrong tries. Wait %(n)s minutes and try again.")
                             % {"n": LOCK_MINUTES}}, status=429)
    profile.save(update_fields=fields)
    left = MAX_TRIES - profile.pin_failures
    return JsonResponse({"ok": False, "error": ngettext(
        "That PIN is wrong. %(n)s try left.", "That PIN is wrong. %(n)s tries left.", left) % {"n": left}}, status=400)


@require_POST
def set_pin(request):
    """Create or change the PIN. Needs the login password, so a phone left signed in can't be used to set one."""
    user = request.user
    pin, again = request.POST.get("pin", ""), request.POST.get("pin2", "")
    if not user.check_password(request.POST.get("password", "")):
        return JsonResponse({"ok": False, "error": _("That password is wrong.")}, status=400)
    if not PIN_RE.match(pin):
        return JsonResponse({"ok": False, "error": _("Use 4 to 6 digits.")}, status=400)
    if pin != again:
        return JsonResponse({"ok": False, "error": _("The two PINs don't match.")}, status=400)
    profile = profile_for(user)
    profile.pin_hash = make_password(pin)
    profile.pin_failures = 0
    profile.pin_locked_until = None
    profile.save(update_fields=["pin_hash", "pin_failures", "pin_locked_until"])
    return JsonResponse({"ok": True, "token": _token_for(user), "message": _("Your PIN is saved.")})


@require_POST
@pin_required
def sign_out_everywhere(request):
    """For a lost phone: every other device is signed out on its next click; this one stays in."""
    profile = profile_for(request.user)
    profile.session_version += 1
    profile.save(update_fields=["session_version"])
    request.session["sv"] = profile.session_version
    messages.success(request, _("All other devices are signed out."))
    return redirect(_back(request))


@receiver(user_logged_in)
def _remember_session_version(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        request.session["sv"] = profile_for(user).session_version


class SessionGuardMiddleware:
    """Signs out a device whose session is older than the last "sign out all other devices"."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, "profile", None)
            if profile is not None:
                seen = request.session.get("sv")
                if seen is None:
                    request.session["sv"] = profile.session_version
                elif seen != profile.session_version:
                    logout(request)
        return self.get_response(request)
