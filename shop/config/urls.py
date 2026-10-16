from django.conf import settings
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.static import serve

from apps.storefront.sitemaps import SITEMAPS
from apps.storefront.views import robots_txt

urlpatterns = [
    path("admin/", include("apps.panel.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("robots.txt", robots_txt),
    path("", include("apps.storefront.urls")),
]

if settings.DEBUG:
    # Chỉ dùng khi phát triển. Production: nginx phục vụ /media/ và /static/.
    urlpatterns += [path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT})]

handler404 = "apps.storefront.errors.not_found"
handler500 = "apps.storefront.errors.server_error"
handler403 = "apps.storefront.errors.forbidden"
