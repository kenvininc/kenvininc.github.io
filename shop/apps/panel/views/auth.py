from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.roles import require_perm
from apps.core.utils import RateLimit, audit, client_ip

from ..forms import ChangeOwnPasswordForm, LoginForm
from .common import safe_next

USER_LIMIT = RateLimit("login-user", 5, 15 * 60)
IP_LIMIT = RateLimit("login-ip", 20, 15 * 60)
ADMIN_SESSION_SECONDS = 8 * 60 * 60


def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("panel:dashboard")
    form = LoginForm(request.POST or None)
    error = ""
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"].strip().lower()
        ip = client_ip(request) or "unknown"
        if USER_LIMIT.is_blocked(username) or IP_LIMIT.is_blocked(ip):
            error = "Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút."
            audit(request, "login_blocked", summary=f"username={username[:50]}")
        else:
            user = authenticate(request, username=form.cleaned_data["username"].strip(), password=form.cleaned_data["password"])
            if user is not None and user.is_active and user.is_staff:
                USER_LIMIT.reset(username)
                login(request, user)
                request.session.set_expiry(ADMIN_SESSION_SECONDS)
                audit(request, "login")
                return redirect(safe_next(request, "/admin/"))
            USER_LIMIT.hit(username)
            IP_LIMIT.hit(ip)
            # Không ghi mật khẩu vào log.
            audit(request, "login_failed", summary=f"username={username[:50]}")
            error = "Tên đăng nhập hoặc mật khẩu không đúng."
    return render(request, "panel/login.html", {"form": form, "error": error, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        audit(request, "logout")
    logout(request)
    messages.success(request, "Đã đăng xuất.")
    return redirect("panel:login")


@require_perm()
def change_password(request):
    form = ChangeOwnPasswordForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["password1"])
        request.user.save()
        update_session_auth_hash(request, request.user)
        audit(request, "password_changed", request.user)
        messages.success(request, "Đã đổi mật khẩu.")
        return redirect("panel:dashboard")
    return render(request, "panel/form_page.html", {"form": form, "title": "Đổi mật khẩu", "submit": "Đổi mật khẩu"})
