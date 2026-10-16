"""Xử lý chuỗi: slug, chuẩn hóa tìm kiếm, định dạng tiền, định dạng nội dung an toàn."""

import re
import unicodedata

from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import slugify


def strip_accents(value: str) -> str:
    value = (value or "").replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if not unicodedata.combining(c))


def vn_slugify(value: str, max_length: int = 180) -> str:
    slug = slugify(strip_accents(value))
    return slug[:max_length].strip("-")


def normalize_search(value: str) -> str:
    """Chuỗi dùng để tìm kiếm không phân biệt hoa thường và dấu tiếng Việt."""
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def format_vnd(amount) -> str:
    """123456 -> '123.456 ₫'. Tiền lưu dạng số nguyên đồng."""
    if amount is None or amount == "":
        return ""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return ""
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,}".replace(",", ".") + " ₫"


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(((?:https?://|/(?![/\\]))[^\s)\\]*)\)")


def _inline(text: str) -> str:
    # text đã được escape; chỉ thêm thẻ do chính hàm này sinh ra.
    text = _BOLD.sub(r"<strong>\1</strong>", text)

    def link(m):
        label, url = m.group(1), m.group(2)
        external = url.startswith("http")
        rel = ' rel="noopener nofollow" target="_blank"' if external else ""
        return f'<a href="{url}"{rel}>{label}</a>'

    return _LINK.sub(link, text)


def render_rich_text(raw: str) -> str:
    """Định dạng nội dung do admin nhập, KHÔNG cho phép HTML.

    Cú pháp hỗ trợ (ghi trong hướng dẫn vận hành):
      - Dòng trống: tách đoạn
      - "## Tiêu đề": tiêu đề nhỏ
      - "- mục": gạch đầu dòng
      - **chữ đậm**
      - [chữ](https://link) hoặc [chữ](/duong-dan)
    """
    if not raw:
        return mark_safe("")
    lines = escape(raw.replace("\r\n", "\n")).split("\n")
    html, para, items = [], [], []

    def flush_para():
        if para:
            html.append("<p>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def flush_list():
        if items:
            html.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_para()
            flush_list()
        elif stripped.startswith("## "):
            flush_para()
            flush_list()
            html.append(f"<h3>{_inline(stripped[3:])}</h3>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            flush_para()
            items.append(stripped[2:])
        else:
            flush_list()
            para.append(stripped)
    flush_para()
    flush_list()
    return mark_safe("".join(html))
