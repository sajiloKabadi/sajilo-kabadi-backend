from django.urls import path

from . import views

app_name = "accounts"

# Sign-in lives in auth_urls.py under /api/v1/auth/.
urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
]
