# weather_utils.py
import requests
import logging

def get_weather_forecast(lat, lon):
    """Fetch current weather from Open-Meteo (free, no API key)."""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        current = data.get('current_weather', {})
        return {
            'temperature': current.get('temperature', 15),
            'wind_speed_mph': current.get('windspeed', 10),
            'conditions': current.get('weathercode', 0),
            'source': 'Open-Meteo'
        }
    except Exception as e:
        logging.error(f"Weather API failed: {e}")
        return {'temperature': 60, 'wind_speed_mph': 15, 'conditions': 'Unknown', 'source': 'fallback'}

def get_weather_hazard_risk(forecast):
    wind = forecast.get('wind_speed_mph', 0)
    if wind > 50:
        return 'high'
    if wind > 30:
        return 'medium'
    return 'low'