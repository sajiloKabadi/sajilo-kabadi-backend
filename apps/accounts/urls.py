from django.urls import path

from . import views

app_name = "accounts"

# Sign-in lives in auth_urls.py under /api/v1/auth/.
urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("me/avatar/", views.AvatarView.as_view(), name="avatar"),
    path("me/device/", views.DeviceView.as_view(), name="device"),
]
