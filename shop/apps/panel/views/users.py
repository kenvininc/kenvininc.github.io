from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import AuditLog
from apps.core.roles import OWNER_ROLE, require_perm
from apps.core.utils import audit

from ..forms import SetPasswordForm, UserCreateForm, UserEditForm, groups_for
from .common import paginate


def _active_owner_count(exclude=None):
    qs = User.objects.filter(is_active=True, is_staff=True, groups__name=OWNER_ROLE)
    if exclude:
        qs = qs.exclude(pk=exclude.pk)
    return qs.distinct().count()


@require_perm("manage_users")
def user_list(request):
    users = User.objects.filter(is_staff=True).prefetch_related("groups").order_by("-is_active", "username")
    return render(request, "panel/users/list.html", {"users": users})


@require_perm("manage_users")
def user_add(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        u = User.objects.create_user(
            username=cd["username"], email=cd["email"], password=cd["password1"], first_name=cd["first_name"], is_staff=True
        )
        u.groups.set(groups_for(cd["roles"]))
        audit(request, "user_create", u, f"{u.username}: {', '.join(cd['roles'])}")
        messages.success(request, f"Đã tạo tài khoản {u.username}.")
        return redirect("panel:users")
    return render(request, "panel/form_page.html", {"form": form, "title": "Thêm tài khoản quản trị", "back": "/admin/tai-khoan/"})


@require_perm("manage_users")
def user_edit(request, pk):
    u = get_object_or_404(User, pk=pk, is_staff=True)
    initial = {"first_name": u.first_name, "email": u.email, "is_active": u.is_active,
               "roles": list(u.groups.values_list("name", flat=True))}
    form = UserEditForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        losing_owner = OWNER_ROLE in initial["roles"] and (OWNER_ROLE not in cd["roles"] or not cd["is_active"])
        if u == request.user and (not cd["is_active"] or OWNER_ROLE not in cd["roles"]) and OWNER_ROLE in initial["roles"]:
            form.add_error(None, "Bạn không thể tự khóa hoặc tự bỏ vai trò Chủ shop của chính mình.")
        elif losing_owner and _active_owner_count(exclude=u) == 0:
            form.add_error(None, "Phải còn ít nhất 1 tài khoản Chủ shop đang hoạt động.")
        else:
            u.first_name, u.email, u.is_active = cd["first_name"], cd["email"], cd["is_active"]
            u.save()
            u.groups.set(groups_for(cd["roles"]))
            audit(request, "user_update", u, f"{u.username}: active={u.is_active}, roles={', '.join(cd['roles'])}")
            messages.success(request, f"Đã lưu tài khoản {u.username}.")
            return redirect("panel:users")
    return render(request, "panel/form_page.html", {
        "form": form, "title": f"Tài khoản {u.username}", "back": "/admin/tai-khoan/",
        "extra_link": (f"/admin/tai-khoan/{u.pk}/mat-khau/", "Đặt lại mật khẩu"),
    })


@require_perm("manage_users")
def user_password(request, pk):
    u = get_object_or_404(User, pk=pk, is_staff=True)
    form = SetPasswordForm(request.POST or None, user=u)
    if request.method == "POST" and form.is_valid():
        u.set_password(form.cleaned_data["password1"])
        u.save()
        audit(request, "user_password_reset", u, u.username)
        messages.success(request, f"Đã đặt mật khẩu mới cho {u.username}. Hãy gửi mật khẩu cho người dùng qua kênh an toàn.")
        return redirect("panel:users")
    return render(request, "panel/form_page.html", {"form": form, "title": f"Đặt lại mật khẩu: {u.username}", "back": "/admin/tai-khoan/"})


@require_perm("view_audit")
def audit_list(request):
    qs = AuditLog.objects.all()
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(action__icontains=q) | Q(summary__icontains=q))
    return render(request, "panel/users/audit.html", {"page_obj": paginate(request, qs, 50)})
