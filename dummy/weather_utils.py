import requests
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache
_cache = {}
_cache_ttl = 300  # 5 minutes

def _get_cached(key):
    if key in _cache:
        data, timestamp = _cache[key]
        if datetime.now() - timestamp < timedelta(seconds=_cache_ttl):
            return data
    return None

def _set_cache(key, data):
    _cache[key] = (data, datetime.now())

# API Keys from environment
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')

def get_weather_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Get real-time weather data from multiple free APIs with fallback."""
    cache_key = f"weather_{lat}_{lon}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # Try OpenWeatherMap first if API key available
    if OPENWEATHER_API_KEY:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=imperial"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                result = {
                    'temperature': data.get('main', {}).get('temp', 60),
                    'wind_speed_mph': data.get('wind', {}).get('speed', 10),
                    'wind_direction': data.get('wind', {}).get('deg', 0),
                    'gust_speed_mph': data.get('wind', {}).get('gust', 0),
                    'conditions': data.get('weather', [{}])[0].get('description', 'Unknown'),
                    'humidity': data.get('main', {}).get('humidity', 50),
                    'pressure': data.get('main', {}).get('pressure', 1013),
                    'source': 'OpenWeatherMap',
                    'timestamp': datetime.now().isoformat()
                }
                _set_cache(cache_key, result)
                logger.info(f"Weather from OpenWeatherMap: {result['wind_speed_mph']} mph")
                return result
        except Exception as e:
            logger.warning(f"OpenWeatherMap failed: {e}")

    # Try NOAA (NWS) as primary free source
    try:
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        headers = {"User-Agent": "PoleRiskPlatform/1.0", "Accept": "application/json"}
        resp = requests.get(points_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            forecast_url = data['properties']['forecast']
            fc_resp = requests.get(forecast_url, headers=headers, timeout=10)
            if fc_resp.status_code == 200:
                fc_data = fc_resp.json()
                period = fc_data['properties']['periods'][0]
                wind_str = period.get('windSpeed', '0 mph')
                wind_val = int(''.join(filter(str.isdigit, wind_str.split()[0]))) if wind_str else 0
                
                # Extract wind direction and gusts
                wind_direction = period.get('windDirection', 0)
                detailed_forecast = period.get('detailedForecast', '')
                
                result = {
                    'temperature': period.get('temperature', 60),
                    'wind_speed_mph': wind_val,
                    'wind_direction': wind_direction,
                    'gust_speed_mph': wind_val * 1.3,  # NOAA doesn't provide gusts in simple forecast
                    'conditions': period.get('shortForecast', 'Unknown'),
                    'humidity': 50,  # Not in simple forecast
                    'pressure': 1013,
                    'source': 'NOAA',
                    'timestamp': datetime.now().isoformat()
                }
                _set_cache(cache_key, result)
                logger.info(f"Weather from NOAA: {wind_val} mph")
                return result
    except Exception as e:
        logger.warning(f"NOAA failed: {e}")

    # Fallback: Open-Meteo (completely free, no API key)
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&wind_speed_unit=mph"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            current = data.get('current_weather', {})
            result = {
                'temperature': current.get('temperature', 60),
                'wind_speed_mph': current.get('windspeed', 10),
                'wind_direction': current.get('winddirection', 0),
                'gust_speed_mph': 0,
                'conditions': 'Unknown',
                'humidity': 50,
                'pressure': 1013,
                'source': 'Open-Meteo',
                'timestamp': datetime.now().isoformat()
            }
            _set_cache(cache_key, result)
            logger.info(f"Weather from Open-Meteo: {result['wind_speed_mph']} mph")
            return result
    except Exception as e:
        logger.error(f"All weather APIs failed: {e}")

    # Ultimate fallback
    result = {
        'temperature': 60,
        'wind_speed_mph': 10,
        'wind_direction': 0,
        'gust_speed_mph': 0,
        'conditions': 'Clear',
        'humidity': 50,
        'pressure': 1013,
        'source': 'fallback',
        'timestamp': datetime.now().isoformat()
    }
    _set_cache(cache_key, result)
    return result


def get_weather_hazard_risk(forecast: Dict) -> str:
    wind = forecast.get('wind_speed_mph', 0)
    gust = forecast.get('gust_speed_mph', 0)
    max_wind = max(wind, gust)
    if max_wind > 50:
        return 'high'
    if max_wind > 30:
        return 'medium'
    return 'low'


def get_storm_alerts(lat: float = None, lon: float = None) -> Dict[str, Any]:
    """Fetch active NOAA storm alerts for the region."""
    cache_key = f"storm_alerts_{lat}_{lon}" if lat and lon else "storm_alerts_default"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        if lat and lon:
            # Get alerts for specific point via NWS
            points_url = f"https://api.weather.gov/points/{lat},{lon}"
            headers = {"User-Agent": "PoleRiskPlatform/1.0", "Accept": "application/json"}
            resp = requests.get(points_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                zone_url = data['properties'].get('forecastZone')
                if zone_url:
                    zone_id = zone_url.split('/')[-1]
                    alerts_url = f"https://api.weather.gov/alerts/active/zone/{zone_id}"
                    alerts_resp = requests.get(alerts_url, headers=headers, timeout=10)
                    if alerts_resp.status_code == 200:
                        return _parse_storm_alerts(alerts_resp.json())
        else:
            # Default: Michigan alerts
            url = "https://api.weather.gov/alerts/active/area/MIZ"
            headers = {"User-Agent": "PoleRiskPlatform/1.0", "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return _parse_storm_alerts(resp.json())
    except Exception as e:
        logger.error(f"Storm alerts fetch failed: {e}")

    # Fallback based on season
    now = datetime.now()
    if now.month in [5,6,7,8]:
        mock_wind = 58
        alert = "WIND ADVISORY"
    else:
        mock_wind = 25
        alert = "No active alerts"
    result = {
        'alerts': [{'headline': alert, 'severity': 'Moderate', 'urgency': 'Expected'}],
        'count': 1,
        'max_forecast_wind_mph': mock_wind,
        'source': 'mock',
        'timestamp': datetime.now().isoformat()
    }
    _set_cache(cache_key, result)
    return result


def _parse_storm_alerts(data):
    features = data.get('features', [])
    alerts = []
    max_wind = 0
    import re
    for f in features:
        props = f.get('properties', {})
        headline = props.get('headline', '')
        description = props.get('description', '')
        alerts.append({
            'headline': headline,
            'severity': props.get('severity', 'Unknown'),
            'urgency': props.get('urgency', 'Unknown'),
            'areas': props.get('areaDesc', ''),
            'effective': props.get('effective', ''),
            'expires': props.get('expires', ''),
            'description': description[:500]
        })
        # Parse wind from description
        numbers = re.findall(r'(\d+)\s*mph', description)
        if numbers:
            max_wind = max(max_wind, max(map(int, numbers)))
    return {
        'alerts': alerts,
        'count': len(alerts),
        'max_forecast_wind_mph': max_wind if max_wind > 0 else 40,
        'source': 'NOAA',
        'timestamp': datetime.now().isoformat()
    }