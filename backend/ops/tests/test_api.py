from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ops.models import Transaction
from ops.tests.factories import make_venue

VALID_TOKEN = "test-token"


@override_settings(POS_INGEST_TOKEN=VALID_TOKEN)
class TransactionIngestTests(TestCase):
    def setUp(self):
        self.venue = make_venue()
        self.url = reverse("transaction-ingest")
        self.payload = {
            "venue_id": self.venue.id,
            "transaction_id": "pos-tx-1",
            "timestamp": timezone.now().isoformat(),
            "type": "sale",
            "items": [{"item_id": "beer", "name": "Beer", "qty": 2, "price": "8.50"}],
            "total": "17.00",
            "staff_id": "staff-9",
        }

    def _post(self, payload=None, token=VALID_TOKEN):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return self.client.post(
            self.url, data=payload or self.payload, content_type="application/json", **headers
        )

    def test_rejects_missing_token(self):
        response = self._post(token=None)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_rejects_wrong_token(self):
        response = self._post(token="wrong-token")
        self.assertEqual(response.status_code, 403)

    def test_creates_transaction_with_valid_token(self):
        response = self._post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Transaction.objects.count(), 1)
        tx = Transaction.objects.get()
        self.assertEqual(tx.items.count(), 1)

    def test_duplicate_transaction_id_is_idempotent(self):
        first = self._post()
        second = self._post()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "duplicate_ignored")
        self.assertEqual(Transaction.objects.count(), 1)

    def test_rejects_unknown_venue(self):
        payload = dict(self.payload, venue_id=999999)
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)

    def test_rejects_invalid_type(self):
        payload = dict(self.payload, type="refunded")
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)


class DashboardAuthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ops", password="pw12345")

    def test_requires_authentication(self):
        response = self.client.get(reverse("dashboard-snapshot"))
        self.assertEqual(response.status_code, 403)

    def test_returns_snapshot_when_authenticated(self):
        self.client.login(username="ops", password="pw12345")
        response = self.client.get(reverse("dashboard-snapshot"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("venues", response.json())


class VenueDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ops", password="pw12345")
        self.venue = make_venue()
        self.client.login(username="ops", password="pw12345")

    def test_404_for_unknown_venue(self):
        response = self.client.get(reverse("venue-detail", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_200_for_known_venue(self):
        response = self.client.get(reverse("venue-detail", args=[self.venue.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["venue_id"], self.venue.id)
