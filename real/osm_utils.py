# osm_utils.py
import requests
import hashlib
import numpy as np
import logging
import time


def fetch_poles_from_osm(bbox: tuple, max_poles: int = 300) -> list:
    """
    Query OpenStreetMap Overpass API for power poles in a bounding box.
    bbox = (south, west, north, east)
    Returns list of pole dicts with id, lat, lon, and OSM tags.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:25];
    (
      node["power"="pole"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out body {max_poles};
    """
    for attempt in range(3):
        try:
            resp = requests.get(overpass_url, params={'data': query}, timeout=20)
            resp.raise_for_status()
            elements = resp.json().get('elements', [])
            poles = [
                {'id': e['id'], 'lat': e['lat'], 'lon': e['lon'],
                 'tags': e.get('tags', {})}
                for e in elements if e.get('type') == 'node'
            ]
            logging.info(f"Fetched {len(poles)} poles from OSM.")
            return poles
        except requests.exceptions.Timeout:
            logging.warning(f"OSM timeout (attempt {attempt+1}/3)")
            time.sleep(2 ** attempt)
        except Exception as e:
            logging.error(f"OSM Overpass error: {e}")
            break
    return []


def enrich_pole_proxy(pole: dict) -> dict:
    """
    Generate deterministic, realistic proxy asset attributes from pole ID.
    Uses pole ID as a random seed so values are stable across requests
    but vary realistically across the pole population.
    """
    seed = int(hashlib.md5(str(pole['id']).encode()).hexdigest()[:8], 16) % 100_000
    rng = np.random.RandomState(seed)

    # Material distribution mirrors real Michigan utility infrastructure
    material_code = int(rng.choice([0, 1, 2], p=[0.55, 0.30, 0.15]))
    material = ['wood', 'steel', 'composite'][material_code]

    age        = int(rng.randint(3, 72))
    tilt       = round(float(rng.uniform(0, 22)), 1)
    cracks     = bool(rng.random() < (0.08 + age * 0.004))   # age-correlated
    rust       = bool(rng.random() < (0.05 + age * 0.003))
    veg_score  = round(float(rng.uniform(1, 10)), 1)
    wind_exp   = ['low', 'medium', 'high'][rng.randint(0, 3)]

    vegetation = 'high' if veg_score > 7 else 'medium' if veg_score > 4 else 'low'

    pole.update({
        'age':            age,
        'material':       material,
        'material_code':  material_code,
        'tilt':           tilt,
        'cracks':         cracks,
        'rust':           rust,
        'veg_score':      veg_score,
        'vegetation':     vegetation,
        'windExposure':   wind_exp,
        'proxy_source':   'osm+deterministic_proxy',
    })
    return pole