from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product
from apps.content.models import Page


class StaticSitemap(Sitemap):
    def items(self):
        return ["store:home", "store:brands", "store:sale", "store:new"]

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    def items(self):
        return Product.objects.visible().order_by("id")

    def lastmod(self, obj):
        return obj.updated_at


class CategorySitemap(Sitemap):
    def items(self):
        return Category.objects.filter(is_active=True)

    def lastmod(self, obj):
        return obj.updated_at


class BrandSitemap(Sitemap):
    def items(self):
        return Brand.objects.filter(is_active=True)


class PageSitemap(Sitemap):
    def items(self):
        return Page.objects.filter(status=Page.Status.PUBLISHED)

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {
    "static": StaticSitemap,
    "products": ProductSitemap,
    "categories": CategorySitemap,
    "brands": BrandSitemap,
    "pages": PageSitemap,
}
