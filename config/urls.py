from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from apps.common.views import health

# Each business module owns its own urls.py; this file only wires prefixes.
api_v1_patterns = [
    path("auth/", include("apps.accounts.auth_urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("sellers/", include("apps.sellers.urls")),
    path("collectors/", include("apps.collectors.urls")),
    path("materials/", include("apps.materials.urls")),
    path("pickups/", include("apps.pickups.urls")),
    path("wallet/", include("apps.wallet.urls")),
    path("dropoff/", include("apps.dropoff.urls")),
    path("impact/", include("apps.impact.urls")),
]

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_patterns)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Unknown /api/ paths get the JSON error envelope; everything else keeps
# Django's HTML pages. Only used when DEBUG=False.
handler404 = "apps.common.views.not_found"
handler500 = "apps.common.views.internal_error"
