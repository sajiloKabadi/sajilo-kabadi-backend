from django.urls import path

from . import views

app_name = "materials"

urlpatterns = [
    path("rates/", views.RateBoardView.as_view(), name="rates"),
]
