import time


class RateLimiter:
    """Token bucket per key: allows short bursts, then a steady rate.

    Each key starts with `capacity` tokens; every action spends one, and tokens refill at
    `refill_per_second`. With capacity 5 and 1/s, someone can send 5 quick messages, then
    about one per second, which stops flooding without getting in the way of real chat.
    """

    def __init__(self, capacity: int = 5, refill_per_second: float = 1.0, clock=time.monotonic):
        self.capacity = capacity
        self.rate = refill_per_second
        self.clock = clock
        self._buckets: dict[object, tuple[float, float]] = {}  # key -> (tokens, last_time)

    def allow(self, key) -> bool:
        now = self.clock()
        tokens, last = self._buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        if tokens < 1:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1, now)
        return True


message_limiter = RateLimiter(capacity=5, refill_per_second=1.0)
