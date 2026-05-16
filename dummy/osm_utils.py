# osm_utils.py
import requests
import logging

def fetch_poles_from_osm(bbox):
    """
    Query OpenStreetMap for real power poles in a bounding box.
    bbox = (south, west, north, east)
    Returns list of poles with id, lat, lon, and basic tags.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["power"="pole"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out body;
    """
    try:
        response = requests.get(overpass_url, params={'data': query}, timeout=15)
        response.raise_for_status()
        data = response.json()
        poles = []
        for element in data.get('elements', []):
            if element.get('type') == 'node':
                poles.append({
                    'id': element.get('id'),
                    'lat': element.get('lat'),
                    'lon': element.get('lon'),
                    'tags': element.get('tags', {})
                })
        logging.info(f"Fetched {len(poles)} real poles from OSM")
        return poles
    except Exception as e:
        logging.error(f"OSM Overpass error: {e}")
        return []