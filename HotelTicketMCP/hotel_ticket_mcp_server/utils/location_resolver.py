"""Resolve a Ctrip location through visible suggestions and the official result URL."""
import re
import time
from urllib.parse import parse_qs, urlsplit
from .location_cache import ResolvedLocation, normalize_name

LOCATION_INPUT = 'css:input[placeholder="位置/品牌/酒店 (选填)"]'
SEARCH_BUTTON = 'css:[role="button"][aria-label="搜索"] button'
CANDIDATES_JS = r"""
const visible = el => {
  if (!el || !el.getClientRects().length || getComputedStyle(el).visibility === 'hidden') return false;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.right <= 0 ||
      rect.top >= innerHeight || rect.left >= innerWidth) return false;
  const x = Math.max(0, Math.min(innerWidth - 1, rect.left + rect.width / 2));
  const y = Math.max(0, Math.min(innerHeight - 1, rect.top + rect.height / 2));
  const hit = document.elementFromPoint(x, y);
  return !!hit && el.contains(hit);
};
const result = [];
const add = (name, detail, el) => {
  if (!visible(el) || !name) return;
  const selector = String(result.length);
  el.setAttribute('data-travel-location-candidate', selector);
  result.push({name, detail, selector});
};
for (const el of document.querySelectorAll('div.f_G6nW5Cv0Pk7f1RIIew')) {
  if (!visible(el)) continue;
  const name = el.textContent.trim();
  const group = el.closest('.N7ro5kT331mx36Af9SmY') || el.parentElement.parentElement;
  const detail = ['.npO9A8vgY_lfKLFDVgG5', '.J_SS12Ra5z4C66UAsqQK', '.v6AKUneePyDOEIk3U_6l']
    .map(selector => (group.querySelector(selector)?.innerText || '').trim()).filter(Boolean).join(' ');
  add(name, detail, el);
  for (const exit of group.querySelectorAll('.rDMes1x8DDoCp36HPNGl')) {
    add(name + '-' + exit.textContent.trim(), detail, exit);
  }
}
return result;
"""


def parse_location_url(url, city_id):
    """The entity type inside searchValue is independent of outer searchType (e.g. MT)."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != "hotels.ctrip.com"
                or parsed.path.rstrip("/") != "/hotels/list" or parsed.username
                or parsed.password or parsed.port not in (None, 443)):
            return None
        query = parse_qs(parsed.query)
        single = lambda key: query[key][0] if len(query.get(key, [])) == 1 else ""
        if single("cityId") != str(city_id):
            return None
        name, outer, value, option = (single(k) for k in ("searchWord", "searchType", "searchValue", "optionId"))
        # Verified layout: entity|id*entity*lat|lng|name|id[|sorting metadata].
        match = re.fullmatch(r"(\d+)\|(\d+)\*(\d+)\*(-?\d+(?:\.\d+)?)\|(-?\d+(?:\.\d+)?)\|([^|]+)\|(\d+)(?:\|.*)?", value)
        if not match or not outer or not name or not option:
            return None
        entity, identifier, repeated_type, lat, lng, value_name, repeated_id = match.groups()
        if (identifier != option or identifier != repeated_id or entity != repeated_type
                or normalize_name(name) != normalize_name(value_name)
                or not -90 <= float(lat) <= 90 or not -180 <= float(lng) <= 180):
            return None
        return ResolvedLocation(str(city_id), name, outer, value, option, entity)
    except (ValueError, KeyError, TypeError):
        return None


def matching_candidates(candidates, requested):
    wanted = normalize_name(requested)
    exact = [c for c in candidates if normalize_name(c["name"]) == wanted]
    if exact:
        return exact
    tokens = [normalize_name(token) for token in re.split(r"\s+", requested.strip()) if token]
    return [c for c in candidates if all(token in normalize_name(c["name"] + c.get("detail", "")) for token in tokens)]


def resolve_location(page, city_id, requested, *, budget=45, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + budget
    remaining = lambda: max(0.01, min(3, deadline - clock()))
    try:
        box = page.ele(LOCATION_INPUT, timeout=remaining())
        if not box:
            return {"status": "unavailable", "reason": "location_input_missing"}
        # Qualifiers are matched locally; the suggestion query uses the place name.
        box.input(re.split(r"\s+", requested.strip())[0], clear=True)
        candidates = []
        # Require stable suggestions: never click a stale city's previous dropdown.
        previous = None
        while clock() < deadline:
            snapshot = page.run_js(CANDIDATES_JS, timeout=remaining()) or []
            candidates = matching_candidates(snapshot, requested)
            signature = [(c["name"], c.get("detail", "")) for c in candidates]
            if signature and signature == previous:
                break
            previous = signature
            sleep(min(0.5, max(0, deadline - clock())))
        else:
            return {"status": "not_found", "reason": "suggestions_timeout"}
        public = [{"name": c["name"], "detail": c.get("detail", "")} for c in candidates]
        if len(candidates) != 1:
            return {"status": "ambiguous", "candidates": public}
        candidate = candidates[0]
        page.ele('css:[data-travel-location-candidate="' + candidate["selector"] + '"]',
                 timeout=remaining()).click(timeout=remaining())
        # Selecting a candidate only fills the field. Submission is a separate action.
        page.ele(SEARCH_BUTTON, timeout=remaining()).click(timeout=remaining())
        while clock() < deadline:
            location = parse_location_url(page.url or "", city_id)
            if location and normalize_name(location.name) == normalize_name(candidate["name"]):
                return {"status": "resolved", "location": location, "candidates": public}
            sleep(min(0.5, max(0, deadline - clock())))
        return {"status": "unavailable", "reason": "selection_not_committed", "candidates": public}
    except Exception as error:
        return {"status": "unavailable", "reason": "browser_" + type(error).__name__}
