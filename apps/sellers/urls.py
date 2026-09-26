from django.urls import path

from . import views

app_name = "sellers"

urlpatterns = [
    path("seller/dashboard/", views.SellerDashboardView.as_view(), name="dashboard"),
    path("me/addresses/", views.AddressListView.as_view(), name="addresses"),
    path("me/addresses/<uuid:pk>/", views.AddressDetailView.as_view(), name="address-detail"),
]
