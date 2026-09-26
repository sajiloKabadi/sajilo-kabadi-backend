from django.urls import path

from . import views

app_name = "collectors"

urlpatterns = [
    path("collector/dashboard/", views.CollectorDashboardView.as_view(), name="dashboard"),
    path("collector/status/", views.CollectorStatusView.as_view(), name="status"),
    path("collector/jobs/", views.JobListView.as_view(), name="jobs"),
    path("collector/jobs/<uuid:pk>/", views.JobDetailView.as_view(), name="job-detail"),
    path("collector/jobs/<uuid:pk>/accept/", views.AcceptJobView.as_view(), name="job-accept"),
    path("collector/jobs/<uuid:pk>/decline/", views.DeclineJobView.as_view(), name="job-decline"),
    path("collector/pickups/<uuid:pk>/status/", views.JobStatusView.as_view(), name="pickup-status"),
    path("collector/location/", views.LocationView.as_view(), name="location"),
    path("collector/pickups/<uuid:pk>/weigh-sheet/", views.CollectorWeighSheetView.as_view(), name="weigh-sheet"),
    path(
        "collector/pickups/<uuid:pk>/weigh-sheet/submit/",
        views.SubmitWeighSheetView.as_view(),
        name="weigh-sheet-submit",
    ),
]
