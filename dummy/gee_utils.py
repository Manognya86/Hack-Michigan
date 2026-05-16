import random
import math
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Try to import Earth Engine (optional)
try:
    import ee  # type: ignore
    EE_AVAILABLE = True
except ImportError:
    EE_AVAILABLE = False
    logger.info("Google Earth Engine not installed")

def get_ndvi(lat: float, lon: float) -> dict:
    """
    Get real NDVI using Google Earth Engine Sentinel-2 data.
    Falls back to location-based estimation if GEE unavailable.
    """
    if EE_AVAILABLE:
        try:
            # Initialize EE if not already
            if not ee.data._initialized:
                ee.Initialize()
            
            point = ee.Geometry.Point(lon, lat)
            # Get Sentinel-2 imagery from last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            collection = (ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
                          .filterBounds(point)
                          .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                          .sort('CLOUDY_PIXEL_PERCENT')
                          .first())
            
            if collection:
                # Calculate NDVI: (NIR - Red) / (NIR + Red)
                ndvi_img = collection.normalizedDifference(['B8', 'B4'])
                ndvi_value = ndvi_img.reduceRegion(ee.Reducer.first(), point, 10).get('nd').getInfo()
                
                if ndvi_value:
                    ndvi = round(float(ndvi_value), 4)
                    
                    # Risk classification from NDVI
                    if ndvi < 0.2:
                        risk = 'low'  # Bare soil, urban
                    elif ndvi < 0.5:
                        risk = 'moderate'  # Sparse vegetation
                    else:
                        risk = 'high'  # Dense vegetation
                    
                    logger.info(f"NDVI from Sentinel-2: {ndvi} ({risk})")
                    return {
                        'ndvi': ndvi,
                        'vegetation_risk': risk,
                        'source': 'Sentinel-2 L2A',
                        'timestamp': datetime.now().isoformat()
                    }
        except Exception as e:
            logger.warning(f"GEE NDVI failed: {e}, falling back to estimation")
    
    # Fallback: location-based NDVI estimation
    return _get_location_based_ndvi(lat, lon)


def _get_location_based_ndvi(lat: float, lon: float) -> dict:
    """Realistic NDVI estimation based on urban proximity and land use."""
    random.seed(int(lat * 1000 + lon * 1000))
    
    # Urban centers (Detroit metro area reference)
    urban_centers = [
        (42.3314, -83.0458),  # Downtown Detroit
        (42.3700, -83.1000),  # Dearborn
        (42.2800, -83.0700),  # Wyandotte
    ]
    
    min_dist = min(
        math.sqrt((lat - uc[0])**2 + (lon - uc[1])**2)
        for uc in urban_centers
    )
    
    if min_dist < 0.05:  # Urban core
        ndvi = round(random.uniform(0.10, 0.25), 4)
        risk = 'low'
    elif min_dist < 0.15:  # Suburban
        ndvi = round(random.uniform(0.25, 0.50), 4)
        risk = 'moderate'
    else:  # Rural / vegetated
        ndvi = round(random.uniform(0.50, 0.80), 4)
        risk = 'high'
    
    return {
        'ndvi': ndvi,
        'vegetation_risk': risk,
        'source': 'location-based-estimate',
        'note': 'Estimated from urban proximity model',
        'timestamp': datetime.now().isoformat()
    }