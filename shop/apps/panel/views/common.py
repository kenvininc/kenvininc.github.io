from django.core.paginator import Paginator
from django.http import HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme

PER_PAGE = 30


def paginate(request, qs, per_page=PER_PAGE):
    return Paginator(qs, per_page).get_page(request.GET.get("trang"))


def safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default


def xlsx_response(content, filename):
    resp = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
