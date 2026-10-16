"""Tạo tài khoản Chủ shop ban đầu (hỏi mật khẩu, không có mật khẩu mặc định).

    python manage.py create_owner --username tenban
"""

import getpass

from django.contrib.auth import password_validation
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.core.roles import OWNER_ROLE, sync_roles


class Command(BaseCommand):
    help = "Tạo tài khoản quản trị với vai trò Chủ shop."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **opts):
        sync_roles()
        username = opts["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(f"Tài khoản {username} đã tồn tại.")
        for _ in range(3):
            p1 = getpass.getpass("Mật khẩu: ")
            p2 = getpass.getpass("Nhập lại mật khẩu: ")
            if p1 != p2:
                self.stderr.write("Mật khẩu nhập lại không khớp.")
                continue
            try:
                password_validation.validate_password(p1, User(username=username))
            except ValidationError as e:
                self.stderr.write(" ".join(e.messages))
                continue
            break
        else:
            raise CommandError("Không tạo tài khoản.")
        user = User.objects.create_user(username=username, email=opts["email"], password=p1, is_staff=True)
        user.groups.add(Group.objects.get(name=OWNER_ROLE))
        self.stdout.write(self.style.SUCCESS(f"Đã tạo tài khoản Chủ shop: {username}. Đăng nhập tại /admin/"))
