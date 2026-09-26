from django.urls import path

from . import views

app_name = "dropoff"

urlpatterns = [
    path("dropoff-centers/", views.DropoffCenterListView.as_view(), name="centers"),
]
