# dte_config.py
import requests
import logging

DTE_SERVICE_TERRITORY = {
    'name': 'DTE Energy — Southeast Michigan',
    'counties': ['Wayne', 'Oakland', 'Macomb', 'Washtenaw', 'Livingston', 'Monroe'],
    'area_sq_miles': 7_600,
    'customer_count': 2_300_000,
    'power_lines_miles': 47_000,
    'service_center_coords': {'lat': 42.3314, 'lon': -83.0458},
    'bounding_box': {'north': 44.0, 'south': 41.5, 'east': -82.0, 'west': -84.5},
}


def get_flood_zone(lat: float, lon: float) -> str:
    """
    Fetch FEMA flood zone from the National Flood Hazard Layer (NFHL) REST API.
    Returns FEMA flood zone string: 'AE' (high risk), 'X' (low risk), etc.
    Free, no API key required.
    Docs: https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer
    """
    url = (
        "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/"
        "MapServer/28/query"
    )
    params = {
        'geometry':     f'{lon},{lat}',
        'geometryType': 'esriGeometryPoint',
        'inSR':         '4326',
        'spatialRel':   'esriSpatialRelIntersects',
        'outFields':    'FLD_ZONE,ZONE_SUBTY',
        'returnGeometry': 'false',
        'f':            'json',
    }
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        features = resp.json().get('features', [])
        if features:
            zone = features[0]['attributes'].get('FLD_ZONE', 'X')
            return zone or 'X'
    except Exception as e:
        logging.warning(f"FEMA NFHL lookup failed for ({lat},{lon}): {e}")
    return 'X'


def soil_risk_from_flood_zone(zone: str) -> int:
    """Convert FEMA zone to binary soil risk flag (0/1) for ML features."""
    high_risk_zones = {'A', 'AE', 'AH', 'AO', 'AR', 'V', 'VE'}
    return 1 if zone in high_risk_zones else 0