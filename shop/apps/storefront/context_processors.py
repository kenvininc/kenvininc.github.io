from django.db.models import Prefetch
from django.utils.functional import SimpleLazyObject

from apps.catalog.models import Category
from apps.content.models import Page
from apps.orders.services import cart_count


def _nav():
    children = Category.objects.filter(is_active=True)
    return list(
        Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related(
            Prefetch("children", queryset=children)
        )
    )


def store(request):
    if request.path.startswith("/admin/"):
        return {}
    return {
        "nav_categories": SimpleLazyObject(_nav),
        "cart_count": SimpleLazyObject(lambda: cart_count(request.session)),
        "footer_pages": SimpleLazyObject(
            lambda: list(Page.objects.filter(status=Page.Status.PUBLISHED, show_in_footer=True))
        ),
    }
