# weather_utils.py
import requests
import logging
from datetime import datetime


def get_weather_forecast(lat: float, lon: float) -> dict:
    """Current weather from Open-Meteo (free, no API key)."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&hourly=precipitation&forecast_days=1"
        )
        resp = requests.get(url, timeout=6)
        data = resp.json()
        cw = data.get('current_weather', {})
        # Convert km/h → mph
        wind_kmh = float(cw.get('windspeed', 0))
        precip_mm = sum(data.get('hourly', {}).get('precipitation', [0])[:24])
        return {
            'temperature_c': cw.get('temperature', 15),
            'wind_speed_mph': round(wind_kmh * 0.621371, 1),
            'wind_direction': cw.get('winddirection', 0),
            'weathercode': cw.get('weathercode', 0),
            'precip_24h_in': round(precip_mm / 25.4, 2),
            'source': 'Open-Meteo',
        }
    except Exception as e:
        logging.error(f"Open-Meteo failed: {e}")
        return {
            'temperature_c': 15,
            'wind_speed_mph': 12,
            'wind_direction': 0,
            'weathercode': 0,
            'precip_24h_in': 0.0,
            'source': 'fallback',
        }


def get_noaa_alerts(lat: float, lon: float) -> dict:
    """
    Fetch active NOAA NWS weather alerts for a point.
    Free REST API — no key required.
    Docs: https://www.weather.gov/documentation/services-web-api
    """
    try:
        headers = {'User-Agent': 'GridWatchAI/1.0 (dtepole@hackmichigan.com)'}
        resp = requests.get(
            f"https://api.weather.gov/alerts/active?point={lat},{lon}",
            headers=headers, timeout=8
        )
        resp.raise_for_status()
        features = resp.json().get('features', [])
        alerts = []
        for f in features[:3]:
            props = f.get('properties', {})
            alerts.append({
                'event':       props.get('event', ''),
                'headline':    props.get('headline', ''),
                'severity':    props.get('severity', 'Unknown'),
                'urgency':     props.get('urgency', 'Unknown'),
                'onset':       props.get('onset', ''),
                'expires':     props.get('expires', ''),
                'description': props.get('description', '')[:300],
            })
        return {
            'has_alerts': len(alerts) > 0,
            'alert_count': len(alerts),
            'alerts': alerts,
            'source': 'NOAA NWS',
            'checked_at': datetime.utcnow().isoformat() + 'Z',
        }
    except Exception as e:
        logging.warning(f"NOAA NWS alerts failed: {e}")
        return {
            'has_alerts': False,
            'alert_count': 0,
            'alerts': [],
            'source': 'fallback',
            'checked_at': datetime.utcnow().isoformat() + 'Z',
        }


def get_weather_hazard_risk(forecast: dict) -> str:
    wind = forecast.get('wind_speed_mph', 0)
    if wind > 50:
        return 'high'
    if wind > 30:
        return 'medium'
    return 'low'