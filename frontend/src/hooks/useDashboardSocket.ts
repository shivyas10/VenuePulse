import { useEffect, useRef } from "react";
import { WS_BASE_URL } from "../api/client";
import type { DashboardSnapshot } from "../types";

/**
 * Owns the single dashboard WebSocket connection and forwards parsed
 * snapshots to the caller. Reconnects with a fixed backoff on drop - an ops
 * session that's open "for hours at a time" needs to survive a blip
 * without the user having to reload the page.
 */
export function useDashboardSocket(onSnapshot: (snapshot: DashboardSnapshot) => void) {
  const callbackRef = useRef(onSnapshot);
  callbackRef.current = onSnapshot;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let closedByClient = false;

    function connect() {
      socket = new WebSocket(`${WS_BASE_URL}/ws/dashboard/`);

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "dashboard.update") {
          callbackRef.current(data.snapshot as DashboardSnapshot);
        }
      };

      socket.onclose = () => {
        if (!closedByClient) {
          reconnectTimer = window.setTimeout(connect, 2000);
        }
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      closedByClient = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);
}
