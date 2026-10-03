"""City-scoped, bounded cache. Only page-verified provider locations may enter it."""
from collections import OrderedDict
from dataclasses import dataclass
import time
import unicodedata


def normalize_name(value):
    return "".join(unicodedata.normalize("NFKC", value or "").split()).casefold()


@dataclass(frozen=True)
class ResolvedLocation:
    city_id: str
    name: str
    search_type: str
    search_value: str
    option_id: str
    entity_type: str

    def public(self):
        return {"resolved_name": self.name, "landmark_id": self.option_id,
                "city_id": self.city_id, "search_type": self.search_type,
                "entity_type": self.entity_type}


class LocationCache:
    def __init__(self, ttl=86400, capacity=256, clock=time.monotonic):
        self.ttl, self.capacity, self.clock = ttl, capacity, clock
        self._entries = OrderedDict()

    def _key(self, city_id, name):
        return "ctrip", str(city_id), normalize_name(name)

    def get(self, city_id, name):
        key = self._key(city_id, name)
        entry = self._entries.get(key)
        if not entry:
            return None
        location, expires = entry
        if self.clock() >= expires:
            self._entries.pop(key)
            return None
        self._entries.move_to_end(key)
        return location

    def put(self, name, location, *, applied):
        # Never promote a short/ambiguous alias to a durable identity.
        if not applied or not location.option_id or normalize_name(name) != normalize_name(location.name):
            return
        key = self._key(location.city_id, name)
        self._entries[key] = (location, self.clock() + self.ttl)
        self._entries.move_to_end(key)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)

    def invalidate(self, city_id, name):
        self._entries.pop(self._key(city_id, name), None)
