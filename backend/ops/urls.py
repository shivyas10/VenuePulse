from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("transactions/", views.TransactionIngestView.as_view(), name="transaction-ingest"),
    path("dashboard/", views.DashboardSnapshotView.as_view(), name="dashboard-snapshot"),
    path("venues/", views.VenueListView.as_view(), name="venue-list"),
    path("venues/<int:venue_id>/detail/", views.VenueDetailView.as_view(), name="venue-detail"),
    path("auth/csrf/", views.CsrfBootstrapView.as_view(), name="auth-csrf"),
    path("auth/login/", views.login_view, name="auth-login"),
    path("auth/logout/", views.logout_view, name="auth-logout"),
    path("auth/session/", views.session_view, name="auth-session"),
]
