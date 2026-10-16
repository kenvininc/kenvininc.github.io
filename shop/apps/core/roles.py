"""Vai trò quản trị và kiểm tra quyền.

Vai trò là Django Group, quyền là các permission khai báo ở core.Permission.
Mọi view trong control panel đều kiểm tra quyền ở backend qua `require_perm`.
"""

from functools import wraps

from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission as AuthPermission
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

ALL_PERMS = [
    "view_dashboard",
    "view_reports",
    "manage_products",
    "manage_prices",
    "manage_stock",
    "import_export",
    "view_orders",
    "manage_orders",
    "manage_payments",
    "manage_promotions",
    "manage_content",
    "manage_settings",
    "manage_users",
    "view_audit",
]

OWNER_ROLE = "Chủ shop"

ROLES = {
    OWNER_ROLE: ALL_PERMS,
    "Quản lý sản phẩm": [
        "view_dashboard",
        "manage_products",
        "manage_prices",
        "manage_stock",
        "import_export",
    ],
    "Xử lý đơn hàng": [
        "view_dashboard",
        "view_orders",
        "manage_orders",
        "manage_payments",
    ],
    "Nội dung": [
        "view_dashboard",
        "manage_content",
    ],
}

ROLE_DESCRIPTIONS = {
    OWNER_ROLE: "Toàn quyền, gồm doanh thu, khuyến mãi, cấu hình và tài khoản.",
    "Quản lý sản phẩm": "Sản phẩm, danh mục, thương hiệu, giá, tồn kho, nhập/xuất Excel.",
    "Xử lý đơn hàng": "Xem và xử lý đơn, vận đơn, trạng thái thanh toán. Không sửa giá.",
    "Nội dung": "Banner, trang nội dung, sản phẩm/danh mục hiển thị trên trang chủ.",
}


def sync_roles():
    """Tạo/cập nhật các Group theo ROLES. Chạy sau migrate."""
    perms = {p.codename: p for p in AuthPermission.objects.filter(content_type__app_label="core")}
    for role, codes in ROLES.items():
        group, _ = Group.objects.get_or_create(name=role)
        group.permissions.set([perms[c] for c in codes if c in perms])


def has_perm(user, code):
    if not user or not user.is_authenticated or not user.is_active or not user.is_staff:
        return False
    return user.has_perm(f"core.{code}")


def require_perm(*codes):
    """Decorator cho view panel: phải đăng nhập, là staff và có ÍT NHẤT MỘT quyền trong codes."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or not user.is_staff or not user.is_active:
                return redirect(f"/admin/dang-nhap/?next={request.path}")
            if codes and not any(has_perm(user, c) for c in codes):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def user_perms(user):
    return {c for c in ALL_PERMS if has_perm(user, c)}
