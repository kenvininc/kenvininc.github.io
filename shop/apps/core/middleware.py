class SecurityHeadersMiddleware:
    """Thêm Content-Security-Policy và các header bảo mật cơ bản.

    Toàn bộ script/style đều là file tĩnh của site, không dùng CDN bên thứ ba.
    """

    CSP = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "object-src 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith("/admin/"):
            response.setdefault("Cache-Control", "no-store")
            response.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response
