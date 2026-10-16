from django import template
from django.templatetags.static import static
from django.utils.html import format_html

from apps.core.text import format_vnd, render_rich_text

register = template.Library()


@register.filter
def vnd(value):
    return format_vnd(value)


@register.filter
def rich(value):
    return render_rich_text(value)


@register.filter
def discount_percent(item):
    """Phần trăm giảm của biến thể/sản phẩm có price và compare_at_price."""
    price = getattr(item, "price", None)
    compare = getattr(item, "compare_at_price", None)
    if not price or not compare or compare <= price:
        return 0
    return round((compare - price) * 100 / compare)


@register.simple_tag
def icon(name, cls="", label=""):
    """SVG icon từ sprite static/img/icons.svg. label rỗng = icon trang trí."""
    href = static("img/icons.svg") + "#" + name
    if label:
        return format_html(
            '<svg class="i {}" role="img" aria-label="{}"><use href="{}"></use></svg>', cls, label, href
        )
    return format_html('<svg class="i {}" aria-hidden="true" focusable="false"><use href="{}"></use></svg>', cls, href)


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def elided(page_obj):
    return page_obj.paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)
