"""Tell drf-spectacular our JWT class is a Bearer scheme, so Swagger's
Authorize button applies to every protected endpoint."""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class ActiveUserJWTScheme(SimpleJWTScheme):
    target_class = "apps.accounts.authentication.ActiveUserJWTAuthentication"
    name = "jwtAuth"
