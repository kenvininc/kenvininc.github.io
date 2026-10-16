from django.contrib.auth.password_validation import MinimumLengthValidator
from django.core.exceptions import ValidationError


class VietnameseMinimumLengthValidator(MinimumLengthValidator):
    """Như MinimumLengthValidator của Django nhưng thông báo bằng tiếng Việt."""

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(f"Mật khẩu quá ngắn, cần ít nhất {self.min_length} ký tự.", code="password_too_short")

    def get_help_text(self):
        return f"Mật khẩu cần ít nhất {self.min_length} ký tự."
