from django.urls import path

from . import views

app_name = "wallet"

urlpatterns = [
    path("wallet/", views.WalletView.as_view(), name="summary"),
    path("wallet/transactions/", views.TransactionListView.as_view(), name="transactions"),
    path("wallet/withdrawals/", views.WithdrawView.as_view(), name="withdrawals"),
    path("wallet/statement/", views.StatementView.as_view(), name="statement"),
    path("wallet/statement/file/", views.StatementFileView.as_view(), name="statement-file"),
    path("me/payout-methods/", views.PayoutMethodListView.as_view(), name="payout-methods"),
    path("me/payout-methods/<uuid:pk>/", views.PayoutMethodDetailView.as_view(), name="payout-method-detail"),
]
