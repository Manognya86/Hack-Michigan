# dte_config.py
import requests
import logging

DTE_SERVICE_TERRITORY = {
    'name': 'DTE Energy - Southeast Michigan',
    'counties': ['Wayne', 'Oakland', 'Macomb', 'Washtenaw', 'Livingston', 'Monroe'],
    'area_sq_miles': 7600,
    'customer_count': 2_300_000,
    'power_lines_miles': 47_000,
    'service_center_coords': {'lat': 42.3314, 'lon': -83.0458},
    'bounding_box': {'north': 44.0, 'south': 41.5, 'east': -82.0, 'west': -84.5}
}

def get_flood_zone(lat, lon):
    """
    Fetch flood zone using FloodTools free API.
    Returns 'AE' (high risk), 'X' (low risk), or 'Unknown'.
    """
    try:
        url = f"https://api.floodtools.org/v1/lookup?lat={lat}&lon={lon}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('zone', 'X')
    except Exception as e:
        logging.warning(f"Flood API failed: {e}")
    return 'X'