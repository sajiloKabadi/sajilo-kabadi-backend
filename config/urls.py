from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from apps.common.views import health

# Each module owns its paths; they are mounted exactly as the contract lists
# them under /api/v1 (v2 contract, section 2.1).
api_v1_patterns = [
    path("auth/", include("apps.accounts.auth_urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.sellers.urls")),
    path("", include("apps.materials.urls")),
    path("", include("apps.pickups.urls")),
    path("", include("apps.dropoff.urls")),
    path("", include("apps.wallet.urls")),
    path("", include("apps.collectors.urls")),
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
