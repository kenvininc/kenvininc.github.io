from django.shortcuts import render


def not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def forbidden(request, exception=None):
    return render(request, "errors/403.html", status=403)


def server_error(request):
    # Không dùng context processor có truy vấn DB: lỗi 500 có thể do chính DB.
    from django.template import loader
    from django.http import HttpResponseServerError

    return HttpResponseServerError(loader.get_template("errors/500.html").render())
