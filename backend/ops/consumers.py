from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from .broadcast import GROUP_NAME


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(GROUP_NAME, self.channel_name)
        await self.accept()

        # Send an immediate snapshot so the dashboard has data before the
        # next scheduled broadcast tick - avoids a blank-screen wait.
        snapshot = await self._build_snapshot()
        await self.send_json({"type": "dashboard.update", "snapshot": snapshot})

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(GROUP_NAME, self.channel_name)

    async def dashboard_update(self, event):
        await self.send_json({"type": "dashboard.update", "snapshot": event["snapshot"]})

    @database_sync_to_async
    def _build_snapshot(self):
        from .aggregation import build_dashboard_snapshot

        return build_dashboard_snapshot()
