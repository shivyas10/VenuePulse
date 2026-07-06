from django.contrib import admin

from .models import Transaction, TransactionItem, Venue


class TransactionItemInline(admin.TabularInline):
    model = TransactionItem
    extra = 0


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "location")
    search_fields = ("name",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("venue", "external_id", "type", "total", "timestamp")
    list_filter = ("type", "venue")
    date_hierarchy = "timestamp"
    inlines = [TransactionItemInline]
