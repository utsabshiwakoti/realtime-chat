import secrets
import time


class TicketStore:
    """Short-lived, single-use tickets for opening WebSockets.

    Browsers can't set headers on a WebSocket, so the credential has to travel in the URL,
    where proxies and access logs can record it. Sending the long-lived JWT there would leak
    a reusable login. Instead the client trades its JWT (in a normal Authorization header)
    for a ticket that works once and expires in seconds, so a logged URL is worthless.

    Kept in memory, like the connection manager: fine for a single process.
    """

    def __init__(self, ttl_seconds: float = 30, clock=time.monotonic):
        self.ttl = ttl_seconds
        self.clock = clock
        self._tickets: dict[str, tuple[int, float]] = {}

    def issue(self, user_id: int) -> str:
        self._purge()
        ticket = secrets.token_urlsafe(32)
        self._tickets[ticket] = (user_id, self.clock() + self.ttl)
        return ticket

    def redeem(self, ticket: str) -> int | None:
        """Return the user id and invalidate the ticket, or None if unknown/expired/used."""
        entry = self._tickets.pop(ticket, None)
        if entry is None:
            return None
        user_id, expires_at = entry
        return user_id if self.clock() < expires_at else None

    def _purge(self) -> None:
        now = self.clock()
        for key in [k for k, (_, exp) in self._tickets.items() if exp <= now]:
            del self._tickets[key]


tickets = TicketStore()
