import ipaddress
import logging

from django.conf import settings
from django.core.cache import cache

from .models import AuditLog

log = logging.getLogger("shop")


def client_ip(request):
    """IP client. Với NUM_PROXIES=N, lấy phần tử thứ N tính từ phải trong X-Forwarded-For.

    Không tin X-Forwarded-For khi NUM_PROXIES=0 vì client có thể tự gửi header này.
    """
    ip = request.META.get("REMOTE_ADDR", "")
    n = settings.NUM_PROXIES
    if n > 0:
        parts = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        if len(parts) >= n:
            ip = parts[-n]
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


class RateLimit:
    """Đếm số lần trong một cửa sổ thời gian, lưu trong cache (database cache)."""

    def __init__(self, scope, limit, window_seconds):
        self.scope, self.limit, self.window = scope, limit, window_seconds

    def _key(self, ident):
        return f"rl:{self.scope}:{ident}"

    def is_blocked(self, ident):
        return (cache.get(self._key(ident)) or 0) >= self.limit

    def hit(self, ident):
        key = self._key(ident)
        if cache.add(key, 1, self.window):
            return 1
        try:
            return cache.incr(key)
        except ValueError:
            cache.set(key, 1, self.window)
            return 1

    def reset(self, ident):
        cache.delete(self._key(ident))


def audit(request, action, target=None, summary=""):
    user = getattr(request, "user", None)
    if user is not None and not user.is_authenticated:
        user = None
    AuditLog.objects.create(
        user=user,
        username=user.get_username() if user else "",
        action=action,
        target_type=target.__class__.__name__ if target is not None else "",
        target_id=str(getattr(target, "pk", "") or "") if target is not None else "",
        summary=summary[:500],
        ip=client_ip(request) if request is not None else None,
    )
