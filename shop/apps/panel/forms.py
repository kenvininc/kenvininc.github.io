from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError

from apps.catalog.models import Attribute, Brand, Category, Product, Variant
from apps.content.models import Banner, Page
from apps.core.models import SiteSettings
from apps.core.roles import ROLE_DESCRIPTIONS, ROLES
from apps.core.text import vn_slugify
from apps.promotions.models import Coupon

DT_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
DT_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []


def _slug_clean(form, model, source_field="name"):
    slug = form.cleaned_data.get("slug") or vn_slugify(form.cleaned_data.get(source_field, ""))
    slug = vn_slugify(slug)
    if not slug:
        raise ValidationError("Đường dẫn không hợp lệ.")
    qs = model.objects.filter(slug=slug)
    if form.instance.pk:
        qs = qs.exclude(pk=form.instance.pk)
    if qs.exists():
        raise ValidationError("Đường dẫn đã được dùng, hãy chọn đường dẫn khác.")
    return slug


class LoginForm(forms.Form):
    username = forms.CharField(label="Tên đăng nhập", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


# ---------------------------------------------------------------- Sản phẩm


class ProductForm(forms.ModelForm):
    slug = forms.CharField(label="Đường dẫn", max_length=200, required=False, help_text="Để trống sẽ tự tạo từ tên.")
    code = forms.CharField(label="Mã sản phẩm", max_length=60, required=False, help_text="Để trống sẽ tự tạo.")
    new_images = MultipleImageField(label="Thêm ảnh", required=False, help_text="Chọn được nhiều ảnh. JPG, PNG, WEBP.")

    class Meta:
        model = Product
        fields = [
            "name", "code", "slug", "brand", "category", "variant_attribute", "status",
            "short_description", "description", "benefits", "ingredients", "usage",
            "is_featured", "is_new", "is_on_sale_section", "seo_title", "seo_description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "benefits": forms.Textarea(attrs={"rows": 5}),
            "ingredients": forms.Textarea(attrs={"rows": 5}),
            "usage": forms.Textarea(attrs={"rows": 5}),
            "short_description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.select_related("parent").order_by("parent__name", "name")
        self.fields["brand"].queryset = Brand.objects.order_by("name")
        self.fields["category"].empty_label = "— Chưa chọn —"
        self.fields["brand"].empty_label = "— Chưa chọn —"
        self.fields["variant_attribute"].empty_label = "— Sản phẩm 1 loại —"

    def clean_slug(self):
        return _slug_clean(self, Product)

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if code:
            qs = Product.objects.filter(code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Mã sản phẩm đã tồn tại.")
        return code


class VariantForm(forms.ModelForm):
    stock = forms.IntegerField(label="Tồn kho", min_value=0, initial=0)
    orig_stock = forms.IntegerField(required=False, widget=forms.HiddenInput)
    orig_price = forms.IntegerField(required=False, widget=forms.HiddenInput)
    orig_compare = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Variant
        fields = ["value", "sku", "price", "compare_at_price", "color_hex", "image", "is_active", "sort_order"]
        widgets = {
            "price": forms.NumberInput(attrs={"min": 0, "step": 1000, "inputmode": "numeric"}),
            "compare_at_price": forms.NumberInput(attrs={"min": 0, "step": 1000, "inputmode": "numeric"}),
            "sort_order": forms.NumberInput(attrs={"style": "width:5em"}),
            "color_hex": forms.TextInput(attrs={"placeholder": "#C0392B", "maxlength": 7}),
        }

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        if product is not None and product.pk:
            self.fields["image"].queryset = product.images.all()
        else:
            self.fields["image"].queryset = Variant.image.field.related_model.objects.none()
        self.fields["image"].empty_label = "— Ảnh chung —"
        self.fields["image"].label_from_instance = lambda img: f"Ảnh {img.sort_order + 1}" + (f" ({img.alt})" if img.alt else "")
        if self.instance.pk:
            self.fields["stock"].initial = self.instance.stock
            self.fields["orig_stock"].initial = self.instance.stock
            self.fields["orig_price"].initial = self.instance.price
            self.fields["orig_compare"].initial = self.instance.compare_at_price

    def clean_sku(self):
        return (self.cleaned_data.get("sku") or "").strip()

    def clean(self):
        cd = super().clean()
        price, compare = cd.get("price"), cd.get("compare_at_price")
        if price is not None and price <= 0:
            self.add_error("price", "Giá bán phải lớn hơn 0.")
        if compare is not None and price is not None and compare <= price:
            self.add_error("compare_at_price", "Giá gốc phải lớn hơn giá bán, hoặc để trống.")
        return cd


class BaseVariantFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.product = kwargs.get("instance")
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kw = super().get_form_kwargs(index)
        kw["product"] = self.product
        return kw

    def clean(self):
        super().clean()
        alive = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not alive:
            raise ValidationError("Sản phẩm phải có ít nhất 1 biến thể (dòng giá/SKU).")
        values = [f.cleaned_data.get("value", "").strip().lower() for f in alive]
        if len(alive) > 1 and any(not v for v in values):
            raise ValidationError("Sản phẩm có nhiều biến thể thì mỗi biến thể phải có “Giá trị biến thể”.")
        if len(set(values)) != len(values):
            raise ValidationError("Các biến thể bị trùng “Giá trị biến thể”.")
        skus = [f.cleaned_data.get("sku") for f in alive]
        if len(set(skus)) != len(skus):
            raise ValidationError("Các biến thể bị trùng SKU.")


VariantFormSet = forms.inlineformset_factory(
    Product, Variant, form=VariantForm, formset=BaseVariantFormSet, extra=0, can_delete=True, min_num=1, validate_min=False
)


class StockAdjustForm(forms.Form):
    MODES = [("add", "Nhập thêm (+)"), ("remove", "Xuất/giảm (−)"), ("set", "Đặt lại theo kiểm kê (=)")]
    mode = forms.ChoiceField(label="Cách điều chỉnh", choices=MODES, widget=forms.RadioSelect, initial="add")
    quantity = forms.IntegerField(label="Số lượng", min_value=0)
    reason = forms.CharField(label="Lý do", max_length=255, help_text="Ví dụ: Nhập hàng NCC, hàng lỗi, kiểm kê cuối tháng.")
    expected = forms.IntegerField(widget=forms.HiddenInput)


class BulkPriceForm(forms.Form):
    OPS = [
        ("pct_up", "Tăng theo %"),
        ("pct_down", "Giảm theo %"),
        ("amt_up", "Tăng số tiền (đ)"),
        ("amt_down", "Giảm số tiền (đ)"),
        ("set", "Đặt giá cố định (đ)"),
        ("sale_pct", "Tạo giảm giá %: giá gốc = giá hiện tại, giá bán giảm %"),
        ("end_sale", "Kết thúc giảm giá: giá bán = giá gốc, bỏ giá gốc"),
    ]
    ROUNDING = [("1", "Không làm tròn"), ("100", "Làm tròn 100đ"), ("1000", "Làm tròn 1.000đ")]
    category = forms.ModelChoiceField(label="Danh mục", queryset=Category.objects.all(), required=False, empty_label="Tất cả")
    brand = forms.ModelChoiceField(label="Thương hiệu", queryset=Brand.objects.all(), required=False, empty_label="Tất cả")
    q = forms.CharField(label="Tên/mã/SKU chứa", required=False, max_length=100)
    operation = forms.ChoiceField(label="Thao tác", choices=OPS)
    amount = forms.IntegerField(label="Giá trị", min_value=0, required=False, help_text="Số % hoặc số tiền tùy thao tác.")
    rounding = forms.ChoiceField(label="Làm tròn", choices=ROUNDING, initial="1000")
    reason = forms.CharField(label="Lý do", max_length=255)

    def clean(self):
        cd = super().clean()
        op, amount = cd.get("operation"), cd.get("amount")
        if op != "end_sale" and not amount:
            self.add_error("amount", "Nhập giá trị.")
        if op in ("pct_down", "sale_pct") and amount and amount >= 100:
            self.add_error("amount", "Phần trăm giảm phải nhỏ hơn 100.")
        return cd


class ImportForm(forms.Form):
    file = forms.FileField(label="File Excel (.xlsx)", widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}))
    auto_create = forms.BooleanField(
        label="Tự tạo thương hiệu, danh mục, loại biến thể chưa có", required=False
    )


class CategoryForm(forms.ModelForm):
    slug = forms.CharField(label="Đường dẫn", max_length=140, required=False, help_text="Để trống sẽ tự tạo từ tên.")
    image_upload = forms.FileField(label="Ảnh/icon", required=False, widget=forms.ClearableFileInput(attrs={"accept": "image/*"}))
    remove_image = forms.BooleanField(label="Xóa ảnh hiện tại", required=False)

    class Meta:
        model = Category
        fields = ["name", "slug", "parent", "description", "sort_order", "is_active", "show_on_home", "seo_title", "seo_description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Category.objects.filter(parent__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = qs
        self.fields["parent"].empty_label = "— Danh mục gốc —"
        self.fields["parent"].help_text = "Hỗ trợ 2 cấp: danh mục gốc và danh mục con."

    def clean_slug(self):
        return _slug_clean(self, Category)

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent and self.instance.pk and self.instance.children.exists():
            raise ValidationError("Danh mục này đang có danh mục con nên không thể đặt làm danh mục con.")
        return parent


class BrandForm(forms.ModelForm):
    slug = forms.CharField(label="Đường dẫn", max_length=140, required=False, help_text="Để trống sẽ tự tạo từ tên.")
    logo_upload = forms.FileField(label="Logo", required=False, widget=forms.ClearableFileInput(attrs={"accept": "image/*"}))
    remove_logo = forms.BooleanField(label="Xóa logo hiện tại", required=False)

    class Meta:
        model = Brand
        fields = ["name", "slug", "description", "sort_order", "is_active", "seo_title", "seo_description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_slug(self):
        return _slug_clean(self, Brand)


class AttributeForm(forms.ModelForm):
    class Meta:
        model = Attribute
        fields = ["name", "is_color", "sort_order"]


# ---------------------------------------------------------------- Đơn hàng


class OrderFilterForm(forms.Form):
    q = forms.CharField(label="Mã đơn, tên, điện thoại", required=False, max_length=100)
    status = forms.ChoiceField(label="Trạng thái", required=False)
    payment_status = forms.ChoiceField(label="Thanh toán", required=False)
    date_from = forms.DateField(label="Từ ngày", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="Đến ngày", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        from apps.orders.models import Order

        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [("", "Tất cả")] + list(Order.Status.choices)
        self.fields["payment_status"].choices = [("", "Tất cả")] + list(Order.PaymentStatus.choices)


class ShippingForm(forms.Form):
    carrier = forms.CharField(label="Đơn vị vận chuyển", max_length=80, required=False)
    tracking_code = forms.CharField(label="Mã vận đơn", max_length=80, required=False)


# ---------------------------------------------------------------- Khuyến mãi


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code", "description", "discount_type", "value", "max_discount", "min_order_value",
            "starts_at", "ends_at", "usage_limit", "usage_limit_per_phone", "is_active",
        ]
        widgets = {"starts_at": DT_WIDGET, "ends_at": DT_WIDGET}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("starts_at", "ends_at"):
            self.fields[f].input_formats = DT_FORMATS
        if self.instance.pk and self.instance.used_count:
            for f in ("code", "discount_type"):
                self.fields[f].disabled = True
                self.fields[f].help_text = "Không sửa được vì mã đã được dùng."

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code.replace("-", "").replace("_", "").isalnum():
            raise ValidationError("Mã chỉ gồm chữ, số, dấu - hoặc _.")
        return code


# ---------------------------------------------------------------- Nội dung


class BannerForm(forms.ModelForm):
    image_upload = forms.FileField(label="Ảnh desktop", required=False, widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
                                   help_text="Banner chính: tỉ lệ khoảng 16:7 (ví dụ 1600×700). Banner phụ: khoảng 2:1.")
    image_mobile_upload = forms.FileField(label="Ảnh điện thoại (tùy chọn)", required=False,
                                          widget=forms.ClearableFileInput(attrs={"accept": "image/*"}))
    remove_mobile = forms.BooleanField(label="Xóa ảnh điện thoại", required=False)

    class Meta:
        model = Banner
        fields = ["title", "placement", "link_url", "sort_order", "is_active", "starts_at", "ends_at"]
        widgets = {"starts_at": DT_WIDGET, "ends_at": DT_WIDGET}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("starts_at", "ends_at"):
            self.fields[f].input_formats = DT_FORMATS
        self.fields["link_url"].help_text = "Ví dụ: /danh-muc/son-moi/ hoặc /san-pham/ten-san-pham/ hoặc /khuyen-mai/"

    def clean(self):
        cd = super().clean()
        if not self.instance.pk and not cd.get("image_upload"):
            self.add_error("image_upload", "Vui lòng chọn ảnh.")
        s, e = cd.get("starts_at"), cd.get("ends_at")
        if s and e and e <= s:
            self.add_error("ends_at", "Thời gian kết thúc phải sau thời gian bắt đầu.")
        return cd


class PageForm(forms.ModelForm):
    slug = forms.CharField(label="Đường dẫn", max_length=120, required=False, help_text="Để trống sẽ tự tạo từ tiêu đề.")

    class Meta:
        model = Page
        fields = ["title", "slug", "body", "status", "show_in_footer", "sort_order", "seo_title", "seo_description"]
        widgets = {"body": forms.Textarea(attrs={"rows": 18})}

    def clean_slug(self):
        return _slug_clean(self, Page, "title")


class SettingsForm(forms.ModelForm):
    logo_upload = forms.FileField(label="Logo", required=False, widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
                                  help_text="PNG nền trong suốt hoặc JPG. Để trống nếu dùng logo chữ.")
    remove_logo = forms.BooleanField(label="Bỏ logo, dùng logo chữ", required=False)

    class Meta:
        model = SiteSettings
        exclude = ["logo", "is_configured"]
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "shipping_policy_summary": forms.Textarea(attrs={"rows": 3}),
            "return_policy_summary": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cd = super().clean()
        if cd.get("bank_transfer_enabled") and not all(
            cd.get(f) for f in ("bank_name", "bank_account_number", "bank_account_name")
        ):
            self.add_error("bank_transfer_enabled", "Cần nhập đủ ngân hàng, số tài khoản và chủ tài khoản.")
        if not cd.get("cod_enabled") and not cd.get("bank_transfer_enabled"):
            self.add_error("cod_enabled", "Cần bật ít nhất 1 phương thức thanh toán để khách đặt hàng được.")
        if cd.get("max_qty_per_item") == 0:
            self.add_error("max_qty_per_item", "Phải lớn hơn 0.")
        return cd


# ---------------------------------------------------------------- Tài khoản


def role_choices():
    return [(name, f"{name} — {ROLE_DESCRIPTIONS.get(name, '')}") for name in ROLES]


class UserCreateForm(forms.Form):
    username = forms.CharField(label="Tên đăng nhập", max_length=150)
    first_name = forms.CharField(label="Họ tên", max_length=150, required=False)
    email = forms.EmailField(label="Email", required=False)
    roles = forms.MultipleChoiceField(label="Vai trò", widget=forms.CheckboxSelectMultiple)
    password1 = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="Tối thiểu 10 ký tự, không quá đơn giản.")
    password2 = forms.CharField(label="Nhập lại mật khẩu", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["roles"].choices = role_choices()

    def clean_username(self):
        u = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=u).exists():
            raise ValidationError("Tên đăng nhập đã tồn tại.")
        return u

    def clean(self):
        cd = super().clean()
        p1, p2 = cd.get("password1"), cd.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Mật khẩu nhập lại không khớp.")
        if p1:
            try:
                password_validation.validate_password(p1, User(username=cd.get("username", "")))
            except ValidationError as e:
                self.add_error("password1", e)
        return cd


class UserEditForm(forms.Form):
    first_name = forms.CharField(label="Họ tên", max_length=150, required=False)
    email = forms.EmailField(label="Email", required=False)
    roles = forms.MultipleChoiceField(label="Vai trò", widget=forms.CheckboxSelectMultiple, required=False)
    is_active = forms.BooleanField(label="Đang hoạt động", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["roles"].choices = role_choices()


class SetPasswordForm(forms.Form):
    password1 = forms.CharField(label="Mật khẩu mới", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="Tối thiểu 10 ký tự, không quá đơn giản.")
    password2 = forms.CharField(label="Nhập lại mật khẩu mới", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cd = super().clean()
        p1, p2 = cd.get("password1"), cd.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Mật khẩu nhập lại không khớp.")
        if p1:
            try:
                password_validation.validate_password(p1, self.user)
            except ValidationError as e:
                self.add_error("password1", e)
        return cd


class ChangeOwnPasswordForm(SetPasswordForm):
    old_password = forms.CharField(label="Mật khẩu hiện tại", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    field_order = ["old_password", "password1", "password2"]

    def clean_old_password(self):
        p = self.cleaned_data["old_password"]
        if not self.user.check_password(p):
            raise ValidationError("Mật khẩu hiện tại không đúng.")
        return p


def groups_for(names):
    return list(Group.objects.filter(name__in=names))
