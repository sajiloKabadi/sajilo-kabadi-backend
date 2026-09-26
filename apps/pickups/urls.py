from django.urls import path

from . import views

app_name = "pickups"

urlpatterns = [
    path("pickups/", views.PickupListCreateView.as_view(), name="list"),
    path("pickups/availability/", views.AvailabilityView.as_view(), name="availability"),
    path("pickups/quote/", views.QuoteView.as_view(), name="quote"),
    path("pickups/<uuid:pk>/", views.PickupDetailView.as_view(), name="detail"),
    path("pickups/<uuid:pk>/cancel/", views.CancelPickupView.as_view(), name="cancel"),
    path("pickups/<uuid:pk>/rating/", views.RatePickupView.as_view(), name="rating"),
    path("pickups/<uuid:pk>/weigh-sheet/", views.WeighSheetView.as_view(), name="weigh-sheet"),
    path("pickups/<uuid:pk>/weigh-sheet/flags/", views.FlagLineView.as_view(), name="weigh-sheet-flags"),
    path("pickups/<uuid:pk>/weigh-sheet/accept/", views.AcceptSheetView.as_view(), name="weigh-sheet-accept"),
    path("disputes/", views.DisputeListCreateView.as_view(), name="disputes"),
]
