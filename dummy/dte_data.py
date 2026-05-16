import math
import random
from datetime import datetime
from data_sources import get_poles_from_osm

def get_real_poles(lat: float, lon: float, radius_km: float = 5.0) -> list:
    """
    Fetch real poles from OSM. If none found, return mock poles for the area.
    """
    poles = get_poles_from_osm(lat, lon, radius_km)
    if poles and len(poles) > 0:
        # Add risk scores to real poles
        for pole in poles:
            compute_pole_risk(pole)
        return poles
    else:
        # Return mock poles based on location
        return generate_mock_poles_for_location(lat, lon)

def generate_mock_poles_for_location(lat: float, lon: float, count: int = 8) -> list:
    """Generate realistic mock poles around the given location."""
    mock_poles = []
    # Base offsets to create a grid around the location
    offsets = [
        (-0.01, -0.01), (-0.01, 0.01), (0.01, -0.01), (0.01, 0.01),
        (-0.005, -0.005), (-0.005, 0.005), (0.005, -0.005), (0.005, 0.005),
        (0, -0.008), (0, 0.008), (-0.008, 0), (0.008, 0)
    ]
    materials = ['wood', 'steel', 'wood', 'composite', 'wood', 'steel']
    districts = ['Downtown', 'North Side', 'South Side', 'East End', 'West End', 'Central']
    
    for i, (dlat, dlng) in enumerate(offsets[:count]):
        pole_id = f"POLE-{1000 + i}"
        pole = {
            'id': pole_id,
            'lat': lat + dlat,
            'lng': lon + dlng,
            'district': random.choice(districts),
            'age': random.randint(5, 50),
            'material': random.choice(materials),
            'tilt': random.uniform(0, 20),
            'cracks': random.choice([True, False]),
            'rust': random.choice([True, False]),
            'vegetation': random.choice(['low', 'medium', 'high']),
            'lastInspection': (datetime.now().replace(year=datetime.now().year - random.randint(1, 5))).strftime('%Y-%m-%d'),
            'circuit': f'C-{random.choice(["SW","DN","DR","LV","AP","WY","HM","IK"])}-{random.randint(1,20):02d}',
            'windExposure': random.choice(['low', 'medium', 'high']),
            'floodZone': random.choice(['X', 'AE', 'B', 'X500']),
            'soilType': random.choice(['Clay', 'Loam', 'Sandy']),
            'source': 'mock'
        }
        compute_pole_risk(pole)
        mock_poles.append(pole)
    return mock_poles

def compute_pole_risk(pole):
    """Calculate risk score (0-100) based on pole properties."""
    score = 0
    age = pole.get('age', 20)
    score += min(age * 1.2, 40)
    tilt = pole.get('tilt', 0)
    score += tilt * 1.8
    if pole.get('cracks', False):
        score += 15
    if pole.get('rust', False):
        score += 10
    veg = pole.get('vegetation', 'medium')
    if veg == 'high':
        score += 12
    elif veg == 'medium':
        score += 6
    wind_exp = pole.get('windExposure', 'medium')
    if wind_exp == 'high':
        score += 10
    elif wind_exp == 'medium':
        score += 5
    flood_zone = pole.get('floodZone', 'X')
    if flood_zone in ['AE', 'A', 'V']:
        score += 8
    elif flood_zone in ['B', 'X500']:
        score += 3
    material = pole.get('material', '').lower()
    if material == 'wood':
        score += 8
    elif material == 'steel':
        score += 4
    last = pole.get('lastInspection')
    if last:
        try:
            last_date = datetime.strptime(last, "%Y-%m-%d")
            years_since = (datetime.now() - last_date).days / 365.25
            score += min(years_since * 3, 12)
        except:
            pass
    raw_score = min(round(score), 100)
    storm_fail_prob = min(raw_score / 100 * 0.85 + 0.05, 0.95)
    remaining_life = max(0.5, (100 - raw_score) / 10)
    if material == 'steel':
        replace_cost = 8500
    elif material == 'composite':
        replace_cost = 11000
    else:
        replace_cost = 6200
    repair_cost = round(replace_cost * 0.35)
    pole['current_risk_score'] = raw_score
    pole['risk_level'] = 'High' if raw_score > 70 else 'Medium' if raw_score > 40 else 'Low'
    pole['storm_fail_prob'] = round(storm_fail_prob, 2)
    pole['remaining_life'] = round(remaining_life, 1)
    pole['replace_cost'] = replace_cost
    pole['repair_cost'] = repair_cost
    return pole

# Keep MOCK_POLES for backward compatibility (will be overwritten by location-based ones)
MOCK_POLES = generate_mock_poles_for_location(42.3314, -83.0458)