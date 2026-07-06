from ops.models import Transaction, TransactionItem, Venue


def make_venue(name="Test Venue", kind=Venue.Kind.PUB):
    return Venue.objects.create(name=name, kind=kind, location="Testville")


def make_transaction(venue, timestamp, tx_type=Transaction.Type.SALE, total="10.00", external_id=None, items=None):
    tx = Transaction.objects.create(
        venue=venue,
        external_id=external_id or f"tx-{Transaction.objects.count()}-{timestamp.timestamp()}",
        timestamp=timestamp,
        type=tx_type,
        total=total,
        staff_id="staff-1",
    )
    for item in items or [{"item_id": "beer", "name": "Beer", "qty": 1, "price": total}]:
        TransactionItem.objects.create(transaction=tx, **item)
    return tx
