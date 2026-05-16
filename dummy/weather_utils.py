# weather_utils.py
import requests
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)

def get_weather_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Return current weather and wind speed using NWS (fallback Open‑Meteo)."""
    try:
        # Try NWS first
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
                return {
                    'temperature': period.get('temperature', 60),
                    'wind_speed_mph': wind_val,
                    'conditions': period.get('shortForecast', 'Unknown'),
                    'source': 'NWS'
                }
    except Exception as e:
        logging.warning(f"NWS failed: {e}")
    # Fallback: Open‑Meteo
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        current = data.get('current_weather', {})
        return {
            'temperature': current.get('temperature', 60),
            'wind_speed_mph': current.get('windspeed', 10),
            'conditions': 'Unknown',
            'source': 'Open-Meteo'
        }
    except Exception as e:
        logging.error(f"Weather API failed: {e}")
        return {'temperature': 60, 'wind_speed_mph': 10, 'conditions': 'Clear', 'source': 'fallback'}

def get_weather_hazard_risk(forecast: Dict) -> str:
    wind = forecast.get('wind_speed_mph', 0)
    if wind > 50:
        return 'high'
    if wind > 30:
        return 'medium'
    return 'low'