from django.conf import settings
from rest_framework.permissions import BasePermission


class HasPosIngestToken(BasePermission):
    """POS terminals are machines, not logged-in ops users - a shared
    bearer token is the right shape of auth here, distinct from the
    session auth the dashboard uses.
    """

    def has_permission(self, request, view):
        expected = f"Bearer {settings.POS_INGEST_TOKEN}"
        return request.headers.get("Authorization", "") == expected
