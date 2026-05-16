import requests
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache with TTL (seconds)
_cache = {}
_cache_ttl = 3600  # 1 hour cache

def _get_cached(key):
    if key in _cache:
        data, timestamp = _cache[key]
        if (datetime.now() - timestamp).total_seconds() < _cache_ttl:
            return data
    return None

def _set_cache(key, data):
    _cache[key] = (data, datetime.now())

# ============================================================
# 1. REAL UTILITY POLE DATA FROM OPENSTREETMAP (Overpass API)
# ============================================================

def get_poles_from_osm(lat: float, lon: float, radius_km: float = 5.0) -> list:
    """
    Fetch real utility pole data from OpenStreetMap using Overpass API.
    Returns list of pole objects with lat, lng, id, and tags.
    """
    cache_key = f"poles_{lat}_{lon}_{radius_km}"
    cached = _get_cached(cache_key)
    if cached:
        logger.info(f"Returning cached poles for {lat},{lon}")
        return cached

    radius_m = radius_km * 1000
    overpass_url = "https://overpass-api.de/api/interpreter"

    # Query for power poles and towers within radius
    query = f"""
    [out:json];
    (
      node["power"="pole"](around:{radius_m},{lat},{lon});
      node["power"="tower"](around:{radius_m},{lat},{lon});
    );
    out body;
    """
    
    try:
        response = requests.post(overpass_url, data=query, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        poles = []
        for element in data.get('elements', []):
            pole = {
                'id': element.get('id'),
                'lat': element.get('lat'),
                'lng': element.get('lon'),
                'power_type': element.get('tags', {}).get('power', 'pole'),
                'material': element.get('tags', {}).get('material', 'unknown'),
                'height': element.get('tags', {}).get('height', None),
                'operator': element.get('tags', {}).get('operator', 'unknown'),
                'voltage': element.get('tags', {}).get('voltage', None),
                'source': 'OpenStreetMap'
            }
            poles.append(pole)
        
        _set_cache(cache_key, poles)
        logger.info(f"Fetched {len(poles)} poles from OSM")
        return poles
        
    except Exception as e:
        logger.error(f"OSM Overpass API error: {e}")
        return []


def get_soil_type(lat: float, lon: float) -> dict:
    """
    Fetch soil type data from OpenLandMap (SoilGrids REST API).
    Returns soil classification for risk assessment.
    """
    cache_key = f"soil_{lat}_{lon}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # SoilGrids REST API endpoint
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    
    payload = {
        "query": {
            "locations": [[lon, lat]],
            "property": ["soc", "clay", "sand", "silt"],
            "depth": ["0-5cm"]
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Extract soil properties
        properties = data.get('properties', {})
        
        # Classify soil type based on sand/clay/silt ratios
        clay = properties.get('clay', {}).get('mean', 25)
        sand = properties.get('sand', {}).get('mean', 40)
        silt = properties.get('silt', {}).get('mean', 35)
        
        # Soil classification for stability
        if clay > 40:
            soil_class = 'clay'
            soil_risk = 0.7  # High instability (expansive)
        elif sand > 60:
            soil_class = 'sandy'
            soil_risk = 0.3  # Low cohesion
        elif silt > 50:
            soil_class = 'silty'
            soil_risk = 0.5
        else:
            soil_class = 'loam'
            soil_risk = 0.2  # Most stable
        
        result = {
            'soil_class': soil_class,
            'soil_risk': soil_risk,
            'clay_percentage': round(clay, 1),
            'sand_percentage': round(sand, 1),
            'silt_percentage': round(silt, 1),
            'source': 'SoilGrids',
            'timestamp': datetime.now().isoformat()
        }
        _set_cache(cache_key, result)
        logger.info(f"Soil data retrieved for {lat},{lon}: {soil_class}")
        return result
        
    except Exception as e:
        logger.warning(f"SoilGrids API error: {e}, using fallback")
        return _get_soil_fallback(lat, lon)


def _get_soil_fallback(lat, lon):
    """Location-based soil approximation when API fails."""
    # Simple latitude-based approximation
    if 40 < lat < 44:
        soil_class = 'clay'
        soil_risk = 0.6
    elif 35 < lat < 40:
        soil_class = 'loam'
        soil_risk = 0.3
    else:
        soil_class = 'sandy'
        soil_risk = 0.5
    return {
        'soil_class': soil_class,
        'soil_risk': soil_risk,
        'source': 'fallback',
        'timestamp': datetime.now().isoformat()
    }


def get_flood_zone(lat: float, lon: float) -> dict:
    """
    Fetch flood zone data from FEMA NFHL.
    Returns flood zone classification for risk assessment.
    """
    cache_key = f"flood_{lat}_{lon}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # FEMA NFHL WMS endpoint for flood zone query
    # Using USGS National Map service as proxy for flood data
    url = f"https://hazards.fema.gov/gis/nfhl/rest/services/NFHL/MapServer/0/query"
    
    params = {
        'geometry': f'{{"x":{lon},"y":{lat}}}',
        'geometryType': 'esriGeometryPoint',
        'inSR': '4326',
        'outSR': '4326',
        'returnGeometry': 'false',
        'returnFields': 'FLD_ZONE,DFIRM_ID',
        'f': 'json'
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        features = data.get('features', [])
        if features:
            attributes = features[0].get('attributes', {})
            flood_zone = attributes.get('FLD_ZONE', 'X')
            
            # Flood risk score based on FEMA zone
            if flood_zone in ['A', 'AE', 'AH', 'AO', 'V', 'VE']:
                flood_risk = 0.8
                risk_level = 'high'
            elif flood_zone in ['B', 'X500']:
                flood_risk = 0.4
                risk_level = 'moderate'
            else:
                flood_risk = 0.1
                risk_level = 'low'
            
            result = {
                'flood_zone': flood_zone,
                'flood_risk': flood_risk,
                'risk_level': risk_level,
                'source': 'FEMA NFHL',
                'timestamp': datetime.now().isoformat()
            }
        else:
            result = {
                'flood_zone': 'X',
                'flood_risk': 0.1,
                'risk_level': 'low',
                'source': 'default',
                'timestamp': datetime.now().isoformat()
            }
            
        _set_cache(cache_key, result)
        logger.info(f"Flood zone data retrieved: {result['flood_zone']}")
        return result
        
    except Exception as e:
        logger.warning(f"FEMA NFHL API error: {e}, using fallback")
        return {
            'flood_zone': 'X',
            'flood_risk': 0.2,
            'risk_level': 'low',
            'source': 'fallback',
            'timestamp': datetime.now().isoformat()
        }


def get_wind_data(lat: float, lon: float) -> dict:
    """
    Get current wind speed and direction from NOAA/Open-Meteo.
    Re-exported from weather_utils for consistency.
    """
    from weather_utils import get_weather_forecast
    weather = get_weather_forecast(lat, lon)
    return {
        'wind_speed_mph': weather.get('wind_speed_mph', 10),
        'wind_direction': weather.get('wind_direction', 0),
        'gust_speed_mph': weather.get('gust_speed_mph', 0),
        'timestamp': weather.get('timestamp', datetime.now().isoformat())
    }