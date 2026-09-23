"""Public auth endpoints, mounted at /api/v1/auth/ (contract sections 2-5)."""

from django.urls import path

from . import views

app_name = "auth"

urlpatterns = [
    path("otp/request/", views.RequestOTPView.as_view(), name="otp-request"),
    path("otp/resend/", views.ResendOTPView.as_view(), name="otp-resend"),
    path("otp/verify/", views.VerifyOTPView.as_view(), name="otp-verify"),
    path("token/refresh/", views.TokenRefreshView.as_view(), name="token-refresh"),
]
