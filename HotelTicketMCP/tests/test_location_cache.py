from dataclasses import replace
from hotel_ticket_mcp_server.utils.location_cache import LocationCache, ResolvedLocation

LOCATION = ResolvedLocation("477", "梨园地铁站", "MT", "provider-value", "16764", "11")


def test_only_verified_exact_names_are_cached_and_cities_are_isolated():
    cache = LocationCache()
    cache.put("梨园地铁站", LOCATION, applied=False)
    cache.put("梨园", LOCATION, applied=True)
    assert cache.get(477, "梨园") is None and cache.get(477, "梨园地铁站") is None
    cache.put("梨园地铁站", LOCATION, applied=True)
    assert cache.get(477, " 梨园地铁站 ") == LOCATION
    assert cache.get(1, "梨园地铁站") is None
    assert cache.get(477, "梨园地铁站-B口") is None


def test_ttl_lru_and_invalidation():
    now = [0]
    cache = LocationCache(ttl=10, capacity=2, clock=lambda: now[0])
    a, b, c = [replace(LOCATION, name=name) for name in "ABC"]
    for location in (a, b):
        cache.put(location.name, location, applied=True)
    cache.get(477, "A")
    cache.put("C", c, applied=True)
    assert cache.get(477, "B") is None
    cache.invalidate(477, "C")
    assert cache.get(477, "C") is None
    now[0] = 10
    assert cache.get(477, "A") is None
