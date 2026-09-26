from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("me/notification-settings/", views.NotificationSettingsView.as_view(), name="settings"),
]
