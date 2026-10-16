from django.urls import path

from . import views

app_name = "store"

urlpatterns = [
    path("", views.home, name="home"),
    path("danh-muc/<slug:slug>/", views.category, name="category"),
    path("thuong-hieu/", views.brand_list, name="brands"),
    path("thuong-hieu/<slug:slug>/", views.brand, name="brand"),
    path("khuyen-mai/", views.sale, name="sale"),
    path("hang-moi/", views.new_arrivals, name="new"),
    path("tim-kiem/", views.search, name="search"),
    path("san-pham/<slug:slug>/", views.product_detail, name="product"),
    path("trang/<slug:slug>/", views.page, name="page"),
    path("gio-hang/", views.cart, name="cart"),
    path("gio-hang/them/", views.cart_add, name="cart_add"),
    path("gio-hang/cap-nhat/", views.cart_update, name="cart_update"),
    path("gio-hang/xoa/", views.cart_remove, name="cart_remove"),
    path("gio-hang/ma-giam-gia/", views.cart_coupon, name="cart_coupon"),
    path("thanh-toan/", views.checkout, name="checkout"),
    path("don-hang/tra-cuu/", views.order_lookup, name="order_lookup"),
    path("don-hang/<str:code>/", views.order_view, name="order_view"),
    path("don-hang/<str:code>/thanh-cong/", views.order_success, name="order_success"),
]
