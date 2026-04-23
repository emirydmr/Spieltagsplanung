"""Geocoding von Spielstätten-Adressen und Berechnung der Entfernungsmatrix."""

import json
import math
import os
import time
from pathlib import Path

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "geocode_cache.json"


def _bereinige_adresse(addr: str) -> list[str]:
    """Erzeugt Suchvarianten für eine Adresse.

    Häufige Probleme in den DFBnet-Adressen:
    - Suffix '-Zentrum', '-Stadtteil' am Ort
    - Vereinsnamen als Prefix ('FC Creglingen, ...')
    - 'Str.' statt 'Straße'
    """
    import re

    varianten = []

    # Original
    varianten.append(f"{addr}, Deutschland")

    # Entferne '-Zentrum' und ähnliche Suffixe am Ende
    cleaned = re.sub(r'-(?:Zentrum|Mitte|Kernstadt)$', '', addr)
    if cleaned != addr:
        varianten.append(f"{cleaned}, Deutschland")

    # Entferne Vereinsnamen-Prefix (z.B. "FC Creglingen, Straße, PLZ Ort")
    # Erkennbar daran, dass > 2 Komma-Teile existieren
    parts = addr.split(", ")
    if len(parts) > 2:
        varianten.append(f"{', '.join(parts[1:])}, Deutschland")

    # Nur PLZ + Ort (Fallback auf Ortsmitte)
    plz_match = re.search(r'(\d{5})\s+(.+)', addr)
    if plz_match:
        plz = plz_match.group(1)
        ort = plz_match.group(2).split('-')[0]  # Ohne Stadtteil
        varianten.append(f"{plz} {ort}, Deutschland")

    return varianten


def _geocode_mit_fallback(geolocator, addr: str, delay: float = 1.1):
    """Versucht mehrere Suchvarianten bis ein Treffer gefunden wird.

    Fallback-Reihenfolge:
    1. Originaladresse
    2. Ohne '-Zentrum'-Suffix
    3. Ohne Vereinsnamen-Prefix
    4. Nur PLZ + Ortsname
    5. Nur PLZ (Stadtmitte)
    """
    import re

    varianten = _bereinige_adresse(addr)

    for variante in varianten:
        try:
            location = geolocator.geocode(variante, timeout=10)
            if location:
                return location
            time.sleep(delay)
        except (GeocoderTimedOut, GeocoderUnavailable):
            time.sleep(delay * 2)

    # Letzter Fallback: nur PLZ -> Stadtmitte
    plz_match = re.search(r'(\d{5})', addr)
    if plz_match:
        try:
            location = geolocator.geocode(f"{plz_match.group(1)}, Deutschland", timeout=10)
            if location:
                print(f"    (Fallback: PLZ {plz_match.group(1)} -> Stadtmitte)")
                return location
            time.sleep(delay)
        except (GeocoderTimedOut, GeocoderUnavailable):
            time.sleep(delay * 2)

    return None


def _load_cache() -> dict[str, dict]:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict[str, dict]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def geocode_adressen(adressen: list[str], delay: float = 1.1) -> dict[str, tuple[float, float]]:
    """Geocodiert eine Liste von Adressen über Nominatim (OpenStreetMap).

    Ergebnisse werden in config/geocode_cache.json gecacht,
    sodass wiederholte Aufrufe keine neuen API-Requests auslösen.

    Args:
        adressen: Liste von Adress-Strings (z.B. "Kirschenwiesen, 74232 Abstatt")
        delay: Sekunden zwischen API-Calls (Nominatim: min 1s)

    Returns:
        Dict: adresse -> (lat, lon). Adressen ohne Ergebnis fehlen.
    """
    cache = _load_cache()
    geolocator = Nominatim(user_agent="spieltagsplaner_bezirk_franken")
    results: dict[str, tuple[float, float]] = {}
    new_lookups = 0

    for addr in adressen:
        key = addr.strip().lower()

        # Aus Cache
        if key in cache:
            entry = cache[key]
            if entry.get("lat") is not None:
                results[addr] = (entry["lat"], entry["lon"])
            continue

        # API-Call mit Fallback-Strategien
        try:
            location = _geocode_mit_fallback(geolocator, addr)

            if location:
                results[addr] = (location.latitude, location.longitude)
                cache[key] = {
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "display": location.address,
                }
                print(f"  OK: {addr} -> ({location.latitude:.4f}, {location.longitude:.4f})")
            else:
                cache[key] = {"lat": None, "lon": None, "display": None}
                print(f"  NICHT GEFUNDEN: {addr}")

            new_lookups += 1
            time.sleep(delay)

        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            print(f"  FEHLER: {addr} -> {e}")
            time.sleep(delay * 2)

    if new_lookups > 0:
        _save_cache(cache)
        print(f"\n{new_lookups} neue Adressen geocodiert, Cache gespeichert.")

    return results


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Berechnet die Luftlinien-Distanz in km zwischen zwei Koordinaten."""
    R = 6371.0  # Erdradius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def berechne_distanzmatrix(
    koordinaten: dict[str, tuple[float, float]],
) -> dict[str, dict[str, float]]:
    """Berechnet die paarweise Distanzmatrix (km Luftlinie) für alle Spielstätten.

    Args:
        koordinaten: Dict von Spielstätten-Key -> (lat, lon)

    Returns:
        Verschachteltes Dict: matrix[a][b] = Distanz in km
    """
    keys = sorted(koordinaten.keys())
    matrix: dict[str, dict[str, float]] = {}

    for a in keys:
        matrix[a] = {}
        lat_a, lon_a = koordinaten[a]
        for b in keys:
            if a == b:
                matrix[a][b] = 0.0
            elif b in matrix and a in matrix[b]:
                matrix[a][b] = matrix[b][a]  # Symmetrie nutzen
            else:
                lat_b, lon_b = koordinaten[b]
                matrix[a][b] = round(haversine_km(lat_a, lon_a, lat_b, lon_b), 1)

    return matrix
