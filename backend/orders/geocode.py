"""Address lookups for the checkout map, through OpenStreetMap's Nominatim.

The browser asks these two views instead of Nominatim, so that we send the
User-Agent Nominatim asks for, cache answers, and keep to its limit of one
request per second: https://operations.osmfoundation.org/policies/nominatim/
"""
import hashlib
import json
import logging
import time
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .forms import is_in_nepal

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
CACHE_SECONDS = 60 * 60 * 24
POKHARA_VIEWBOX = "83.85,28.35,84.15,28.10"
logger = logging.getLogger(__name__)


def _may_ask_nominatim():
    """At most one request a second. add() only stores the key if it isn't there,
    and the key disappears after a second. (Django's default cache is per server
    process; with several processes use a shared cache such as Redis.)"""
    return cache.add("geocode:last-request", True, timeout=1)


def _ask_nominatim(path, params):
    """Nominatim's JSON answer, or None if it failed."""
    url = f"{NOMINATIM_URL}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={
        "User-Agent": settings.NOMINATIM_USER_AGENT,
        "Accept-Language": "en",
    })
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)
    except (OSError, ValueError):  # no connection, timeout, error status or bad JSON
        logger.warning("Nominatim request failed: %s", path, exc_info=True)
        return None


def _busy():
    return JsonResponse({"error": "Too many lookups. Please try again in a moment."}, status=429)


def _unavailable():
    return JsonResponse({"error": "The map lookup isn't working right now."}, status=502)


def _road(parts):
    return parts.get("road") or parts.get("pedestrian") or parts.get("footway")


def _reverse(lat, lng, zoom):
    """Nominatim's reverse answer. Zoom 18 finds buildings, 17 streets, 16 main streets."""
    return _ask_nominatim("/reverse", {
        "format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lng:.5f}", "zoom": zoom, "addressdetails": 1,
    })


def _wait_for_our_turn():
    """Before another request in the same lookup: wait (at most 3 seconds) until the
    one-a-second limit lets us ask again."""
    for _ in range(3):
        time.sleep(1)
        if _may_ask_nominatim():
            return True
    return False


def _nearest_road(lat, lng):
    """'Near <road>' from a wider look around the point (zoom 17, then 16), or ""."""
    for zoom in (17, 16):
        if not _wait_for_our_turn():
            return ""  # other lookups have the turns; the customer can still type the street
        data = _reverse(lat, lng, zoom)
        if not isinstance(data, dict):
            return ""
        road = _road(data.get("address") or {})
        if road:
            return f"Near {road}"
    return ""


def _place_texts(data):
    """A suggested landmark, street, city and area from a Nominatim reverse answer."""
    parts = data.get("address") or {}
    road = _road(parts)
    area = parts.get("neighbourhood") or parts.get("suburb") or parts.get("quarter")
    place = parts.get("city") or parts.get("town") or parts.get("village") or parts.get("municipality")
    address = ", ".join(part for part in (road, area, place) if part)
    # The road and area, or the area alone. A city alone ("Pokhara") isn't a street, so
    # then it stays empty and reverse_geocode looks for the nearest road.
    street = ", ".join(part for part in (road, area) if part)
    # Saved with a map pin (Address.city). A village isn't counted as a city.
    city = parts.get("city") or parts.get("town") or parts.get("municipality") or ""
    # The area and town without the road, e.g. "Pokhara": the order's address when the
    # customer gives only a landmark.
    area_text = ", ".join(part for part in (area, place) if part)
    # A shop, amenity (school, temple, bank...) or named building at the pin. Else the named
    # place the pin is on (e.g. a hotel), unless that is only the road or the town.
    # A shop, amenity, building, tourism, office or named place at the pin.
    nearby = (
        parts.get("amenity")
        or parts.get("shop")
        or parts.get("building")
        or parts.get("tourism")
        or parts.get("office")
        or parts.get("leisure")
        or parts.get("historic")
    )
    if not nearby and data.get("name") not in (road, area, place):
        nearby = data.get("name")

    if nearby:
        landmark = f"Near {nearby}"
    else:
        # Fallback to neighbourhood, suburb, quarter, or road
        fallback = (
            parts.get("neighbourhood")
            or parts.get("suburb")
            or parts.get("quarter")
            or road
        )
        landmark = f"Near {fallback}" if fallback else ""

    return {"landmark": landmark, "street": street, "city": city, "area": area_text, "address": address}


@login_required
@require_GET
def reverse_geocode(request):
    """GET ?lat=&lng= -> {"landmark", "street", "city", "area", "address"} for the map pin."""
    try:
        lat = float(request.GET["lat"])
        lng = float(request.GET["lng"])
    except (KeyError, ValueError):
        return JsonResponse({"error": "lat and lng must be numbers."}, status=400)
    if not is_in_nepal(lat, lng):  # also false for NaN and infinity
        return JsonResponse({"error": "That point is outside Nepal."}, status=400)

    # 5 decimal places is about 1 metre, so taps close together share an answer.
    key = f"geocode:reverse:{lat:.5f},{lng:.5f}"
    result = cache.get(key)
    if result is None:
        if not _may_ask_nominatim():
            return _busy()
        data = _reverse(lat, lng, 18)
        if not isinstance(data, dict):
            return _unavailable()
        result = _place_texts(data)
        if not result["street"]:
            # Nothing at the exact point, e.g. between roads: give the nearest road.
            # This can keep the request waiting a few seconds, but the answer is cached.
            result["street"] = _nearest_road(lat, lng)
        if not result.get("landmark") and result.get("street"):
            st = result["street"]
            result["landmark"] = st if st.startswith("Near ") else f"Near {st}"
        cache.set(key, result, CACHE_SECONDS)
    return JsonResponse(result)


@login_required
@require_GET
def search_geocode(request):
    """GET ?q= -> {"results": [{"name", "lat", "lng"}, ...]}, places in Nepal only."""
    query = request.GET.get("q", "").strip()
    if not 3 <= len(query) <= 100:
        return JsonResponse({"error": "Type 3 to 100 letters to search."}, status=400)

    viewbox = request.GET.get("viewbox", POKHARA_VIEWBOX).strip() or POKHARA_VIEWBOX
    # Hashed so the cache key is short and safe whatever was typed.
    key = "geocode:search:" + hashlib.sha256(f"{query.lower()}:{viewbox}".encode()).hexdigest()
    result = cache.get(key)
    if result is None:
        if not _may_ask_nominatim():
            return _busy()
        data = _ask_nominatim("/search", {
            
            "format": "jsonv2",
            "q": query,
            "countrycodes": "np",
            "viewbox": viewbox,
            "limit": 5,
        })
        if not isinstance(data, list):
            return _unavailable()
        places = []
        for item in data:
            try:
                lat, lng = float(item["lat"]), float(item["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if is_in_nepal(lat, lng):
                places.append({"name": item.get("display_name", ""), "lat": lat, "lng": lng})
        result = {"results": places}
        cache.set(key, result, CACHE_SECONDS)
    return JsonResponse(result)
