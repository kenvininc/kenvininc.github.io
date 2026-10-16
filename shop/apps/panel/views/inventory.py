from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalog.models import PriceHistory, Product, StockMovement, Variant
from apps.catalog.services import ConcurrentChange, adjust_stock, set_price
from apps.core.models import SiteSettings
from apps.core.roles import require_perm
from apps.core.text import normalize_search
from apps.core.utils import audit

from ..forms import BulkPriceForm, StockAdjustForm
from .common import paginate

BULK_SESSION_KEY = "bulk_price_preview"
BULK_MAX_ROWS = 1000


@require_perm("manage_stock", "manage_products")
def stock_list(request):
    site = SiteSettings.load()
    qs = Variant.objects.select_related("product", "product__brand").order_by("stock", "product__name")
    q = (request.GET.get("q") or "").strip()
    if q:
        for t in normalize_search(q).split():
            qs = qs.filter(product__search_text__icontains=t)
    level = request.GET.get("muc", "")
    if level == "het":
        qs = qs.filter(stock__lte=0)
    elif level == "sap-het":
        qs = qs.filter(stock__lte=site.low_stock_threshold)
    if request.GET.get("an") != "1":
        qs = qs.filter(is_active=True).exclude(product__status=Product.Status.HIDDEN)
    return render(request, "panel/inventory/stock.html", {"page_obj": paginate(request, qs), "threshold": site.low_stock_threshold})


@require_perm("manage_stock")
def stock_adjust(request, pk):
    v = get_object_or_404(Variant.objects.select_related("product"), pk=pk)
    form = StockAdjustForm(request.POST or None, initial={"expected": v.stock})
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        qty = cd["quantity"]
        delta = {"add": qty, "remove": -qty, "set": qty - cd["expected"]}[cd["mode"]]
        try:
            new = adjust_stock(v.pk, delta, StockMovement.Kind.ADJUST, user=request.user, reason=cd["reason"], expected=cd["expected"])
        except ConcurrentChange as e:
            messages.error(request, str(e))
            return redirect("panel:stock_adjust", pk=v.pk)
        except ValueError as e:
            form.add_error("quantity", str(e))
        else:
            audit(request, "stock_adjust", v, f"{v.sku}: {delta:+d} → {new}. {cd['reason']}")
            messages.success(request, f"Đã cập nhật tồn kho {v.sku}: {cd['expected']} → {new}.")
            return redirect("panel:stock")
    movements = v.stock_movements.select_related("user", "order_item__order")[:20]
    return render(request, "panel/inventory/adjust.html", {"form": form, "variant": v, "movements": movements})


@require_perm("manage_stock", "manage_products")
def stock_history(request):
    qs = StockMovement.objects.select_related("variant", "variant__product", "user", "order_item__order")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(variant__sku__icontains=q) | Q(variant__product__name__icontains=q) | Q(reason__icontains=q))
    kind = request.GET.get("loai", "")
    if kind in StockMovement.Kind.values:
        qs = qs.filter(kind=kind)
    return render(request, "panel/inventory/stock_history.html", {"page_obj": paginate(request, qs), "kinds": StockMovement.Kind.choices})


@require_perm("manage_prices", "manage_products")
def price_history(request):
    qs = PriceHistory.objects.select_related("variant", "variant__product", "changed_by")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(variant__sku__icontains=q) | Q(variant__product__name__icontains=q))
    return render(request, "panel/inventory/price_history.html", {"page_obj": paginate(request, qs)})


def _round(value, step):
    if step <= 1:
        return value
    return int((value + step // 2) // step * step)


def compute_bulk(variants, op, amount, step):
    """Trả về list dòng xem trước: (variant, new_price, new_compare, warning)."""
    rows = []
    for v in variants:
        price, compare = v.price, v.compare_at_price
        warn = ""
        if op == "pct_up":
            price = _round(v.price * (100 + amount) // 100, step)
        elif op == "pct_down":
            price = _round(v.price * (100 - amount) // 100, step)
        elif op == "amt_up":
            price = v.price + amount
        elif op == "amt_down":
            price = v.price - amount
        elif op == "set":
            price = amount
        elif op == "sale_pct":
            compare = v.compare_at_price if v.is_discounted else v.price
            price = _round(compare * (100 - amount) // 100, step)
        elif op == "end_sale":
            if v.is_discounted:
                price, compare = v.compare_at_price, None
        if price <= 0:
            warn = "Giá mới ≤ 0, sẽ bỏ qua."
        elif compare is not None and compare <= price:
            compare = None
            warn = "Giá bán ≥ giá gốc nên sẽ bỏ giá gốc."
        rows.append((v, price, compare, warn))
    return rows


@require_perm("manage_prices")
def bulk_price(request):
    form = BulkPriceForm(request.POST or None)
    preview = None
    if request.method == "POST" and request.POST.get("step") == "confirm":
        return _bulk_confirm(request)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        qs = Variant.objects.select_related("product").filter(is_active=True).order_by("product__name", "sort_order")
        if cd["category"]:
            qs = qs.filter(Q(product__category=cd["category"]) | Q(product__category__parent=cd["category"]))
        if cd["brand"]:
            qs = qs.filter(product__brand=cd["brand"])
        if cd["q"]:
            for t in normalize_search(cd["q"]).split():
                qs = qs.filter(product__search_text__icontains=t)
        variants = list(qs[: BULK_MAX_ROWS + 1])
        if len(variants) > BULK_MAX_ROWS:
            form.add_error(None, f"Có hơn {BULK_MAX_ROWS} biến thể phù hợp, hãy thu hẹp điều kiện lọc.")
        elif not variants:
            form.add_error(None, "Không có biến thể nào phù hợp điều kiện.")
        else:
            rows = compute_bulk(variants, cd["operation"], cd["amount"] or 0, int(cd["rounding"]))
            changed = [r for r in rows if r[1] > 0 and (r[1], r[2]) != (r[0].price, r[0].compare_at_price)]
            request.session[BULK_SESSION_KEY] = {
                "reason": cd["reason"],
                "op": dict(BulkPriceForm.OPS)[cd["operation"]],
                "rows": [[v.pk, v.price, v.compare_at_price, p, c] for v, p, c, _w in changed],
            }
            preview = {"rows": rows, "changed": len(changed), "reason": cd["reason"]}
    return render(request, "panel/inventory/bulk_price.html", {"form": form, "preview": preview})


def _bulk_confirm(request):
    data = request.session.pop(BULK_SESSION_KEY, None)
    if not data or not data["rows"]:
        messages.error(request, "Không có dữ liệu xem trước, vui lòng thực hiện lại.")
        return redirect("panel:bulk_price")
    try:
        with transaction.atomic():
            ids = [r[0] for r in data["rows"]]
            locked = {v.pk: v for v in Variant.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
            for vid, old_p, old_c, new_p, new_c in data["rows"]:
                v = locked.get(vid)
                if v is None:
                    raise ConcurrentChange("Có biến thể đã bị xóa sau khi xem trước.")
                set_price(v, new_p, new_c, request.user, PriceHistory.Source.BULK, data["reason"], expected=(old_p, old_c))
    except ConcurrentChange as e:
        messages.error(request, f"{e} Không có giá nào được thay đổi. Vui lòng xem trước lại.")
        return redirect("panel:bulk_price")
    audit(request, "price_bulk", summary=f"{data['op']}: {len(data['rows'])} biến thể. Lý do: {data['reason']}")
    messages.success(request, f"Đã cập nhật giá {len(data['rows'])} biến thể.")
    return redirect("panel:price_history")
