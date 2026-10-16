import re
import uuid

from django import forms

PHONE_RE = re.compile(r"^0\d{9,10}$")


def normalize_phone(value):
    digits = re.sub(r"[^\d+]", "", value or "")
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits.replace("+", "")


class PhoneField(forms.CharField):
    def clean(self, value):
        value = super().clean(value)
        phone = normalize_phone(value)
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("Số điện thoại chưa đúng. Ví dụ: 0912345678.")
        return phone


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(
        label="Họ và tên",
        max_length=120,
        error_messages={"required": "Vui lòng nhập họ tên người nhận."},
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    phone = PhoneField(
        label="Số điện thoại",
        max_length=20,
        error_messages={"required": "Vui lòng nhập số điện thoại."},
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    email = forms.EmailField(
        label="Email (không bắt buộc)",
        required=False,
        help_text="Nhập email nếu muốn nhận xác nhận đơn hàng qua email.",
        error_messages={"invalid": "Email chưa đúng định dạng."},
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    address = forms.CharField(
        label="Địa chỉ giao hàng",
        max_length=500,
        min_length=10,
        help_text="Số nhà, đường, phường/xã, quận/huyện, tỉnh/thành phố.",
        error_messages={
            "required": "Vui lòng nhập địa chỉ giao hàng.",
            "min_length": "Địa chỉ quá ngắn, vui lòng ghi đầy đủ hơn.",
        },
        widget=forms.Textarea(attrs={"rows": 3, "autocomplete": "street-address"}),
    )
    customer_note = forms.CharField(
        label="Ghi chú (không bắt buộc)",
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    payment_method = forms.ChoiceField(
        label="Phương thức thanh toán",
        widget=forms.RadioSelect,
        error_messages={"required": "Vui lòng chọn phương thức thanh toán."},
    )
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, payment_methods=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = list(payment_methods)
        if len(payment_methods) == 1:
            self.fields["payment_method"].initial = payment_methods[0][0]
        if not self.is_bound:
            self.initial["idempotency_key"] = uuid.uuid4()


class LookupForm(forms.Form):
    code = forms.CharField(
        label="Mã đơn hàng",
        max_length=20,
        error_messages={"required": "Vui lòng nhập mã đơn hàng."},
        widget=forms.TextInput(attrs={"autocapitalize": "characters", "placeholder": "Ví dụ: KS2610161A2B"}),
    )
    phone = PhoneField(
        label="Số điện thoại đặt hàng",
        max_length=20,
        error_messages={"required": "Vui lòng nhập số điện thoại."},
        widget=forms.TextInput(attrs={"inputmode": "tel"}),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()
