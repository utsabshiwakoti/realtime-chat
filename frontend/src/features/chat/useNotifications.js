import { useEffect, useRef } from "react";
import { openSocket } from "../../api/client";

// One socket per tab that hears about new messages in *any* room or DM the user is in,
// so the sidebar can show unread badges for rooms that aren't open.
export default function useNotifications(token, onActivity) {
  // Keep the latest callback without reconnecting every time it changes.
  const callback = useRef(onActivity);
  useEffect(() => {
    callback.current = onActivity;
  }, [onActivity]);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    let retries = 0;
    let timer;
    let ws;

    function retry() {
      if (cancelled) return;
      timer = setTimeout(connect, Math.min(1000 * 2 ** retries, 30000));
      retries += 1;
    }

    async function connect() {
      try {
        ws = await openSocket("/ws/notifications");
      } catch {
        retry();
        return;
      }
      if (cancelled) return ws.close();
      ws.onopen = () => (retries = 0);
      ws.onmessage = (e) => {
        const event = JSON.parse(e.data);
        if (event.type === "activity") callback.current(event);
      };
      ws.onclose = retry;
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [token]);
}
