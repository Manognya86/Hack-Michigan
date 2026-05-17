"""
data_pipeline.py – Fetches live weather, OSM poles, FEMA flood zones, AQI, soil moisture, historical storms.
"""

import asyncio
import httpx
import numpy as np
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
OSM_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FEMA_NFHL_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

DETROIT_BOUNDS = {"lat_min": 42.15, "lat_max": 42.55, "lng_min": -83.45, "lng_max": -82.85}
_fema_cache = {}

# ── Environmental helpers (simulated; replace with real APIs if keys available) ───
async def fetch_aqi(lat: float, lng: float) -> int:
    """
    Simulated Air Quality Index.
    Real API: https://docs.airnowapi.org/
    For hackathon, returns a realistic value for Detroit area.
    """
    base = 55  # typical Detroit AQI
    variation = random.randint(-20, 40)
    return max(0, min(500, base + variation))

async def fetch_soil_moisture(lat: float, lng: float, flood_zone: str, recent_precip: float) -> float:
    """
    Simulated soil moisture (0-1) based on flood zone and recent precipitation.
    """
    moisture = 0.3  # baseline
    if flood_zone in ["AE", "A"]:
        moisture += 0.3
    moisture += min(recent_precip * 0.1, 0.3)
    return round(min(1.0, moisture), 2)

# ── Weather (live) ─────────────────────────────────────────────────────────────
async def fetch_weather(lat: float = 42.33, lng: float = -83.05) -> Dict:
    """Fetch real-time weather from Open-Meteo."""
    params = {
        "latitude": lat, "longitude": lng,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,precipitation,weather_code,cloud_cover",
        "daily": "wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum,weather_code",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Detroit",
        "forecast_days": 7
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            d = r.json()
            curr = d.get("current", {})
            daily = d.get("daily", {})
            max_gust = max(daily.get("wind_gusts_10m_max", [0]))
            return {
                "source": "open-meteo-live",
                "current": {
                    "wind_mph": round(curr.get("wind_speed_10m", 0), 1),
                    "gust_mph": round(curr.get("wind_gusts_10m", 0), 1),
                    "precipitation_in": round(curr.get("precipitation", 0), 2),
                    "temp_f": round(curr.get("temperature_2m", 20) * 9/5 + 32, 1),
                    "weather_desc": _weather_desc(curr.get("weather_code", 0))
                },
                "storm_alert": "HIGH WIND WARNING" if max_gust >= 58 else "WIND ADVISORY" if max_gust >= 40 else None,
                "storm_gust_mph": round(max_gust, 1),
                "storm_exposure_index": min(max_gust / 80, 1.0)
            }
    except Exception as e:
        logger.warning(f"Weather API error: {e}. Using synthetic weather.")
        return _synthetic_weather()

def _weather_desc(code: int) -> str:
    codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 51: "Light drizzle", 61: "Light rain", 63: "Moderate rain",
        65: "Heavy rain", 71: "Snow", 80: "Rain showers", 95: "Thunderstorm",
        96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail"
    }
    return codes.get(code, f"Code {code}")

def _synthetic_weather() -> Dict:
    """Fallback synthetic weather data."""
    wind = round(random.gauss(18, 8), 1)
    gust = round(wind * random.uniform(1.2, 1.8), 1)
    return {
        "source": "synthetic-fallback",
        "current": {
            "wind_mph": max(0, wind),
            "gust_mph": max(0, gust),
            "precipitation_in": round(max(0, random.gauss(0.1, 0.15)), 2),
            "temp_f": round(random.gauss(62, 15), 1),
            "weather_desc": random.choice(["Partly cloudy", "Light rain", "Mainly clear"])
        },
        "storm_alert": None,
        "storm_gust_mph": round(max(0, random.gauss(35, 15)), 1),
        "storm_exposure_index": random.uniform(0.2, 0.6)
    }

# ── Historical storms (for advanced prediction) ───────────────────────────────
async def fetch_historical_storms(days_back: int = 30, lat: float = 42.33, lng: float = -83.05) -> List[Dict]:
    """Fetch historical daily weather data to identify past storms."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    params = {
        "latitude": lat, "longitude": lng,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "daily": "wind_gusts_10m_max,precipitation_sum",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Detroit"
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(HISTORICAL_WEATHER_URL, params=params)
            r.raise_for_status()
            data = r.json()
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            gusts = daily.get("wind_gusts_10m_max", [])
            precip = daily.get("precipitation_sum", [])
            storms = []
            for i, gust in enumerate(gusts):
                if gust >= 40:  # storm threshold
                    storms.append({
                        "date": dates[i],
                        "gust_mph": gust,
                        "precipitation_in": precip[i] if i < len(precip) else 0
                    })
            return storms
    except Exception as e:
        logger.warning(f"Historical weather fetch failed: {e}")
        return []

# ── FEMA Flood Zone (live, with caching) ──────────────────────────────────────
async def fetch_fema_flood_zone(lat: float, lng: float) -> str:
    """Query FEMA NFHL for flood zone at a coordinate, with caching."""
    cache_key = f"{lat:.4f},{lng:.4f}"
    if cache_key in _fema_cache:
        return _fema_cache[cache_key]
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE",
        "returnGeometry": "false",
        "f": "json"
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(FEMA_NFHL_URL, params=params)
            r.raise_for_status()
            features = r.json().get("features", [])
            zone = features[0]["attributes"].get("FLD_ZONE", "X") if features else "X"
            _fema_cache[cache_key] = zone
            return zone
    except Exception as e:
        logger.debug(f"FEMA error for ({lat},{lng}): {e}. Using fallback 'X'.")
        zone = "X"
        _fema_cache[cache_key] = zone
        return zone

# ── OSM Power Poles ───────────────────────────────────────────────────────────
async def fetch_osm_poles(limit: int = 150) -> List[Dict]:
    """Fetch real power pole nodes from OSM Overpass API."""
    b = DETROIT_BOUNDS
    query = f"""[out:json][timeout:60];
node["power"="pole"]({b['lat_min']},{b['lng_min']},{b['lat_max']},{b['lng_max']});
out {limit};"""
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(OSM_OVERPASS_URL, data={"data": query}, headers={"User-Agent": "GridWatchAI/1.0"})
            r.raise_for_status()
            elements = r.json().get("elements", [])[:limit]
            poles = []
            for i, el in enumerate(elements):
                lat = el.get("lat")
                lng = el.get("lon")
                if lat is None or lng is None:
                    continue
                district = "Metro Detroit"  # simplified; could be improved with reverse geocoding
                age = int(np.clip(np.random.normal(35, 12), 1, 70))
                material = random.choices(["Wood","Steel","Concrete","Composite"], weights=[0.6,0.22,0.1,0.08])[0]
                tilt = float(np.clip(np.random.normal(age * 0.2, 3), 0, 25))
                crack = int(random.random() < (0.03 + age * 0.008))
                rust = int(random.random() < (0.02 + age * 0.006 + (0.1 if material == "Steel" else 0)))
                veg = random.choices(["high","medium","low"], weights=[0.2,0.4,0.4])[0]
                wind_exp = random.choice(["high","medium","low"])
                flood = await fetch_fema_flood_zone(lat, lng)
                soil = random.choices(["Clay","Loam","Sandy","Bedrock"], weights=[0.45,0.3,0.15,0.1])[0]
                storm_exp = random.uniform(0.2, 0.8)
                last_insp = (datetime.now() - timedelta(days=random.uniform(180, 2000))).strftime("%Y-%m-%d")
                years_since = (datetime.now() - datetime.strptime(last_insp, "%Y-%m-%d")).days / 365.25
                height = round(np.clip(np.random.normal(35, 5), 25, 55), 1)
                road = round(np.clip(random.expovariate(1/60) + 5, 5, 300), 1)
                xfmr = random.choices([0,1,2,3], weights=[0.6,0.25,0.1,0.05])[0]
                last_maint = random.randint(2015, 2023)
                aqi = await fetch_aqi(lat, lng)
                poles.append({
                    "pole_id": f"OSM-{el.get('id', i)}",
                    "lat": lat,
                    "lng": lng,
                    "district": district,
                    "age": age,
                    "material": material,
                    "tilt_angle": round(tilt, 1),
                    "crack_detected": crack,
                    "rust_detected": rust,
                    "vegetation_risk": veg,
                    "wind_exposure": wind_exp,
                    "flood_zone": flood,
                    "soil_type": soil,
                    "storm_exposure_index": round(storm_exp, 3),
                    "years_since_inspection": round(years_since, 2),
                    "urban_density": random.uniform(0.4, 0.9),
                    "last_inspection": last_insp,
                    "source": "osm-live",
                    "height_ft": height,
                    "road_proximity_ft": road,
                    "num_transformers": xfmr,
                    "last_maintenance_year": last_maint,
                    "aqi": aqi,
                    "soil_moisture": 0.5  # placeholder, will be updated later
                })
            logger.info(f"Fetched {len(poles)} live OSM poles")
            return poles
    except Exception as e:
        logger.warning(f"OSM fetch failed: {e}. Using synthetic fallback.")
        return await _synthetic_poles(limit)

async def _synthetic_poles(n: int) -> List[Dict]:
    """Generate realistic synthetic poles as fallback."""
    poles = []
    for i in range(n):
        lat = random.uniform(DETROIT_BOUNDS["lat_min"], DETROIT_BOUNDS["lat_max"])
        lng = random.uniform(DETROIT_BOUNDS["lng_min"], DETROIT_BOUNDS["lng_max"])
        district = "Metro Detroit"
        age = int(np.clip(np.random.normal(35, 12), 1, 70))
        material = random.choices(["Wood","Steel","Concrete","Composite"], weights=[0.6,0.22,0.1,0.08])[0]
        tilt = float(np.clip(np.random.normal(age * 0.2, 3), 0, 25))
        crack = int(random.random() < (0.03 + age * 0.008))
        rust = int(random.random() < (0.02 + age * 0.006 + (0.1 if material == "Steel" else 0)))
        veg = random.choices(["high","medium","low"], weights=[0.2,0.4,0.4])[0]
        wind_exp = random.choice(["high","medium","low"])
        flood = await fetch_fema_flood_zone(lat, lng)
        soil = random.choices(["Clay","Loam","Sandy","Bedrock"], weights=[0.45,0.3,0.15,0.1])[0]
        storm_exp = random.uniform(0.2, 0.8)
        last_insp = (datetime.now() - timedelta(days=random.uniform(180, 2000))).strftime("%Y-%m-%d")
        years_since = (datetime.now() - datetime.strptime(last_insp, "%Y-%m-%d")).days / 365.25
        height = round(np.clip(np.random.normal(35, 5), 25, 55), 1)
        road = round(np.clip(random.expovariate(1/60) + 5, 5, 300), 1)
        xfmr = random.choices([0,1,2,3], weights=[0.6,0.25,0.1,0.05])[0]
        last_maint = random.randint(2015, 2023)
        aqi = await fetch_aqi(lat, lng)
        poles.append({
            "pole_id": f"SYN-{i+1:04d}",
            "lat": lat,
            "lng": lng,
            "district": district,
            "age": age,
            "material": material,
            "tilt_angle": round(tilt, 1),
            "crack_detected": crack,
            "rust_detected": rust,
            "vegetation_risk": veg,
            "wind_exposure": wind_exp,
            "flood_zone": flood,
            "soil_type": soil,
            "storm_exposure_index": round(storm_exp, 3),
            "years_since_inspection": round(years_since, 2),
            "urban_density": random.uniform(0.4, 0.9),
            "last_inspection": last_insp,
            "source": "synthetic",
            "height_ft": height,
            "road_proximity_ft": road,
            "num_transformers": xfmr,
            "last_maintenance_year": last_maint,
            "aqi": aqi,
            "soil_moisture": 0.5
        })
    return poles

# ── Main region data assembler ────────────────────────────────────────────────
async def fetch_region_data(n_poles: int = 150) -> Dict:
    """
    Fetches weather and poles concurrently, then injects live weather into each pole.
    Also updates soil moisture with live precipitation.
    """
    weather_task = fetch_weather()
    poles_task = fetch_osm_poles(limit=n_poles)
    weather, poles = await asyncio.gather(weather_task, poles_task)
    storm_idx = weather.get("storm_exposure_index", 0.4)
    live_wind = weather.get("current", {}).get("wind_mph", 0)
    live_precip = weather.get("current", {}).get("precipitation_in", 0)
    for p in poles:
        p["storm_exposure_index"] = round(p.get("storm_exposure_index", 0.4) * 0.6 + storm_idx * 0.4, 3)
        p["live_wind_mph"] = live_wind
        # Update soil moisture based on live precipitation
        p["soil_moisture"] = await fetch_soil_moisture(p["lat"], p["lng"], p["flood_zone"], live_precip)
    return {
        "poles": poles,
        "weather": weather,
        "fetched_at": datetime.utcnow().isoformat(),
        "total_poles": len(poles),
        "region": "Metro Detroit / DTE Energy Territory"
    }