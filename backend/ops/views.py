from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction as db_transaction
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .aggregation import build_dashboard_snapshot, build_venue_detail
from .broadcast import broadcast_snapshot_update
from .models import Transaction, Venue
from .permissions import HasPosIngestToken
from .serializers import TransactionIngestSerializer


class HealthView(APIView):
    """Unauthenticated liveness check for container orchestration and for
    the simulator to wait on before it starts posting transactions."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class TransactionIngestView(APIView):
    """POST /api/transactions/ - the POS write path.

    Idempotent on (venue, transaction_id): a POS retrying a delivery after
    a dropped response re-sends the same payload, and that must not double
    count the sale. We rely on a DB unique constraint rather than a
    check-then-insert, since the latter races under concurrent writes from
    many venues.

    Authenticated with a shared POS ingest token, not the ops session -
    this endpoint is called by POS terminals, not logged-in dashboard users.
    """

    authentication_classes = []
    permission_classes = [HasPosIngestToken]

    def post(self, request):
        serializer = TransactionIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        external_id = serializer.validated_data["transaction_id"]
        venue_id = serializer.validated_data["venue_id"]

        existing = Transaction.objects.filter(venue_id=venue_id, external_id=external_id).first()
        if existing is not None:
            return Response({"status": "duplicate_ignored", "transaction_id": external_id}, status=status.HTTP_200_OK)

        try:
            with db_transaction.atomic():
                obj = serializer.save()
                db_transaction.on_commit(broadcast_snapshot_update)
        except IntegrityError:
            # Lost the race with a concurrent identical request; treat the
            # same as the pre-check duplicate case.
            return Response({"status": "duplicate_ignored", "transaction_id": external_id}, status=status.HTTP_200_OK)

        return Response({"status": "created", "transaction_id": obj.external_id}, status=status.HTTP_201_CREATED)


class DashboardSnapshotView(APIView):
    """GET /api/dashboard/ - initial page load, before the socket connects."""

    def get(self, request):
        return Response(build_dashboard_snapshot())


class VenueDetailView(APIView):
    """GET /api/venues/<id>/detail/ - backs the drill-down modal."""

    def get(self, request, venue_id):
        if not Venue.objects.filter(pk=venue_id).exists():
            raise Http404("venue not found")
        return Response(build_venue_detail(venue_id))


class VenueListView(APIView):
    def get(self, request):
        venues = Venue.objects.all().values("id", "name", "kind", "location")
        return Response(list(venues))


class CsrfBootstrapView(APIView):
    """GET /api/auth/csrf/ - sets the csrftoken cookie for the SPA to read
    before its first POST (login). Django's CSRF middleware requires a
    token even on the login request itself, so the frontend needs to grab
    a cookie from somewhere before that first unsafe request.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"detail": "CSRF cookie set"})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username", "")
    password = request.data.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
    login(request, user)
    return Response({"username": user.username})


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def session_view(request):
    return Response({"username": request.user.username})
