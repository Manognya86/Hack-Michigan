# damage_assessment.py
import random
import logging

def detect_vegetation_loss(lat, lon, storm_date):
    """Mock vegetation loss detection. Real implementation would use GEE change detection."""
    loss = random.uniform(0, 0.6)
    if loss > 0.4:
        severity = 'Severe'
    elif loss > 0.2:
        severity = 'Moderate'
    else:
        severity = 'Low'
    return {
        'vegetation_loss_percentage': round(loss * 100, 2),
        'severity': severity,
        'ndvi_pre': round(random.uniform(0.4, 0.8), 2),
        'ndvi_post': round(random.uniform(0.1, 0.6), 2)
    }