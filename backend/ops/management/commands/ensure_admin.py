import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Idempotently creates the default ops-dashboard login (safe to run on every startup)."

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("OPS_ADMIN_USERNAME", "ops_admin")
        password = os.environ.get("OPS_ADMIN_PASSWORD", "ops-admin-pass123")

        user, created = User.objects.get_or_create(
            username=username, defaults={"is_staff": True, "is_superuser": True}
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created default login: {username}"))
        else:
            self.stdout.write(f"Login '{username}' already exists - leaving as-is.")
