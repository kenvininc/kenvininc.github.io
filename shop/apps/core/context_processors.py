from django.utils.functional import SimpleLazyObject

from .models import SiteSettings
from .roles import user_perms


def site(request):
    def perms():
        return user_perms(request.user) if hasattr(request, "user") else set()

    return {
        "site": SimpleLazyObject(SiteSettings.load),
        "panel_perms": SimpleLazyObject(perms),
    }
