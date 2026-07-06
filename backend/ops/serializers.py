from decimal import Decimal

from rest_framework import serializers

from .models import Transaction, TransactionItem, Venue


class TransactionItemInputSerializer(serializers.Serializer):
    item_id = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=200)
    qty = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))


class TransactionIngestSerializer(serializers.Serializer):
    """Validates an inbound POS transaction payload.

    Deliberately a plain Serializer (not a ModelSerializer) - the wire
    format (`transaction_id`, flat `items[]`) doesn't match the storage
    shape 1:1, and `create()` fans out into two tables inside one
    atomic write, so an explicit serializer keeps that translation visible.
    """

    venue_id = serializers.IntegerField()
    transaction_id = serializers.CharField(max_length=64)
    timestamp = serializers.DateTimeField()
    type = serializers.ChoiceField(choices=Transaction.Type.choices)
    items = TransactionItemInputSerializer(many=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    staff_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def validate_venue_id(self, value):
        if not Venue.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f"Unknown venue_id {value}")
        return value

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        transaction = Transaction.objects.create(
            venue_id=validated_data["venue_id"],
            external_id=validated_data["transaction_id"],
            timestamp=validated_data["timestamp"],
            type=validated_data["type"],
            total=validated_data["total"],
            staff_id=validated_data.get("staff_id", ""),
        )
        TransactionItem.objects.bulk_create(
            [
                TransactionItem(
                    transaction=transaction,
                    item_id=item["item_id"],
                    name=item["name"],
                    qty=item["qty"],
                    price=item["price"],
                )
                for item in items_data
            ]
        )
        return transaction
