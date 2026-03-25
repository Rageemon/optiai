"""
Nominatim Geocoding Client
===========================
Free geocoding via OpenStreetMap Nominatim.
Rate limit: max 1 request per second (enforced by this module).

Usage
-----
    from app.solvers.map_routing.nominatim_client import geocode

    lat, lng = geocode("Times Square, New York City")
"""

from __future__ import annotations

import logging
import time
import urllib.parse

import requests

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "OptimAI-MapRouting/1.0 (optimization-engine)"}
_last_call: float = 0.0   # module-level timestamp for rate limiting


def geocode(address: str, timeout: int = 10) -> tuple[float, float]:
    """
    Convert a free-text address to (latitude, longitude).

    Raises
    ------
    ValueError  — if the address cannot be geocoded.
    RuntimeError — on HTTP/network error.
    """
    global _last_call

    # Enforce Nominatim's 1 req/s policy
    elapsed = time.monotonic() - _last_call
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    params = {
        "q": address,
        "format": "json",
        "limit": 1,
    }
    url = f"{_NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    logger.debug("Geocoding: %s", address)

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        _last_call = time.monotonic()
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Nominatim request failed: {exc}") from exc

    data = resp.json()
    if not data:
        raise ValueError(
            f"Could not geocode address: '{address}'. "
            "Try a more specific location (e.g., add city/country)."
        )

    lat = float(data[0]["lat"])
    lng = float(data[0]["lon"])
    logger.info("Geocoded '%s' → (%.6f, %.6f)", address, lat, lng)
    return lat, lng


def reverse_geocode(lat: float, lng: float, timeout: int = 10) -> str:
    """
    Convert (latitude, longitude) to a human-readable address string.
    Returns a short display name; falls back to coordinate string on failure.
    """
    global _last_call

    elapsed = time.monotonic() - _last_call
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lng}&format=json"
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        _last_call = time.monotonic()
        resp.raise_for_status()
        return resp.json().get("display_name", f"{lat:.5f}, {lng:.5f}")
    except Exception:
        return f"{lat:.5f}, {lng:.5f}"
