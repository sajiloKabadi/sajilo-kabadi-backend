from django.middleware.common import CommonMiddleware


class ApiCommonMiddleware(CommonMiddleware):
    """CommonMiddleware without APPEND_SLASH for /api/ paths.

    A POST to a slashless path would otherwise get a 301 to the slashed one,
    and most HTTP clients follow it as a body-less GET, so the request shows
    up empty and looks like a validation bug. For the API we answer 404
    instead so the mistake is loud. Admin and other HTML pages keep the
    redirect.
    """

    def should_redirect_with_slash(self, request):
        if request.path_info.startswith("/api/"):
            return False
        return super().should_redirect_with_slash(request)
