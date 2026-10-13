"""Address lookups for the checkout map, through OpenStreetMap's Nominatim.

The browser asks these two views instead of Nominatim, so that we send the
User-Agent Nominatim asks for, cache answers, and keep to its limit of one
request per second: https://operations.osmfoundation.org/policies/nominatim/
"""
import hashlib
import json
import logging
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


def _place_texts(data):
    """A suggested landmark and address line from a Nominatim reverse answer."""
    parts = data.get("address") or {}
    road = parts.get("road") or parts.get("pedestrian") or parts.get("footway")
    area = parts.get("neighbourhood") or parts.get("suburb") or parts.get("quarter")
    city = parts.get("city") or parts.get("town") or parts.get("village") or parts.get("municipality")
    address = ", ".join(part for part in (road, area, city) if part)
    landmark = f"Near {data['name']}" if data.get("name") else ""
    return {"landmark": landmark, "address": address}


@login_required
@require_GET
def reverse_geocode(request):
    """GET ?lat=&lng= -> {"landmark": ..., "address": ...} for the map pin."""
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
        data = _ask_nominatim("/reverse", {
            "format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lng:.5f}", "zoom": 18, "addressdetails": 1,
        })
        if not isinstance(data, dict):
            return _unavailable()
        result = _place_texts(data)
        cache.set(key, result, CACHE_SECONDS)
    return JsonResponse(result)


@login_required
@require_GET
def search_geocode(request):
    """GET ?q= -> {"results": [{"name", "lat", "lng"}, ...]}, places in Nepal only."""
    query = request.GET.get("q", "").strip()
    if not 3 <= len(query) <= 100:
        return JsonResponse({"error": "Type 3 to 100 letters to search."}, status=400)

    # Hashed so the cache key is short and safe whatever was typed.
    key = "geocode:search:" + hashlib.sha256(query.lower().encode()).hexdigest()
    result = cache.get(key)
    if result is None:
        if not _may_ask_nominatim():
            return _busy()
        data = _ask_nominatim("/search", {"format": "jsonv2", "q": query, "countrycodes": "np", "limit": 5})
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
