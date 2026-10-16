"""Kiểm tra và chuẩn hóa ảnh upload.

- Chỉ nhận JPEG/PNG/WEBP, kiểm tra bằng nội dung file (Pillow), không tin phần mở rộng.
- Giới hạn dung lượng và số pixel.
- Ảnh được mở và LƯU LẠI thành WEBP với tên ngẫu nhiên: bỏ metadata/EXIF,
  bỏ mọi dữ liệu lạ chèn trong file gốc, phần mở rộng luôn là .webp.
"""

import io
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000


def _open_checked(uploaded):
    max_bytes = settings.MAX_IMAGE_UPLOAD_MB * 1024 * 1024
    if uploaded.size > max_bytes:
        raise ValidationError(f"Ảnh vượt quá {settings.MAX_IMAGE_UPLOAD_MB} MB.")
    uploaded.seek(0)
    data = uploaded.read()
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError("File không phải ảnh hợp lệ (chỉ nhận JPG, PNG, WEBP).")
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Chỉ nhận ảnh JPG, PNG hoặc WEBP.")
    img = Image.open(io.BytesIO(data))
    if img.width * img.height > MAX_PIXELS:
        raise ValidationError("Ảnh có kích thước quá lớn.")
    try:
        img.load()
    except (OSError, Image.DecompressionBombError):
        raise ValidationError("Không đọc được nội dung ảnh.")
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
    return img


def _encode(img, max_side, quality=85):
    out = img.copy()
    out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="WEBP", quality=quality, method=4)
    return buf.getvalue()


def process_upload(uploaded, max_side=1600, thumb_side=480):
    """Trả về (ContentFile ảnh lớn, ContentFile thumbnail hoặc None)."""
    img = _open_checked(uploaded)
    name = uuid.uuid4().hex
    main = ContentFile(_encode(img, max_side), name=f"{name}.webp")
    thumb = ContentFile(_encode(img, thumb_side, 80), name=f"{name}_t.webp") if thumb_side else None
    return main, thumb


def validate_image_upload(uploaded):
    _open_checked(uploaded)
