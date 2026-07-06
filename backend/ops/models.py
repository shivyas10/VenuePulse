from django.db import models


class Venue(models.Model):
    class Kind(models.TextChoices):
        PUB = "pub", "Pub"
        RESTAURANT = "restaurant", "Restaurant"
        FUNCTION_SPACE = "function_space", "Function space"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PUB)
    location = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Transaction(models.Model):
    class Type(models.TextChoices):
        SALE = "sale", "Sale"
        VOID = "void", "Void"
        REFUND = "refund", "Refund"

    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="transactions")
    # The POS's own transaction id. Unique per venue (not globally), since
    # independent POS terminals across venues are not guaranteed to
    # coordinate on a shared id space.
    external_id = models.CharField(max_length=64)
    timestamp = models.DateTimeField(db_index=True)
    type = models.CharField(max_length=10, choices=Type.choices, db_index=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    staff_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "external_id"], name="unique_venue_transaction"
            )
        ]
        indexes = [
            models.Index(fields=["venue", "timestamp"]),
            models.Index(fields=["timestamp", "type"]),
        ]

    def __str__(self):
        return f"{self.venue_id}:{self.external_id} ({self.type})"


class TransactionItem(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="items")
    item_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    qty = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        indexes = [
            models.Index(fields=["item_id"]),
        ]

    def __str__(self):
        return f"{self.qty}x {self.name}"
