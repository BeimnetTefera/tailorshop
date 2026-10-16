from django.conf import settings
from django.utils import translation


class UserLanguageMiddleware:
    """Show each person the app in their chosen language (saved on their profile).

    Before signing in, the choice comes from a cookie so the login page can switch too.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, "profile", None)
            language = profile.language if profile else None
        language = language or request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if language not in dict(settings.LANGUAGES):
            language = settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = language
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", language)
        return response
