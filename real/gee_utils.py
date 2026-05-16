# gee_utils.py
import ee
import logging

GEE_AVAILABLE = False
try:
    ee.Initialize()
    GEE_AVAILABLE = True
    logging.info("Google Earth Engine ready")
except:
    logging.warning("GEE not available, will use fallback")

def get_ndvi(lat, lon):
    """Return NDVI and vegetation risk. Falls back to mock if GEE unavailable."""
    if not GEE_AVAILABLE:
        return {'ndvi': 0.45, 'vegetation_risk': 'moderate', 'source': 'mock'}
    try:
        point = ee.Geometry.Point(lon, lat)
        collection = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                      .filterBounds(point)
                      .filterDate('2024-01-01', '2025-12-31')
                      .sort('CLOUD_COVER'))
        image = collection.first()
        if image is None:
            return {'ndvi': None, 'error': 'No imagery', 'source': 'error'}
        optical = image.select('SR_B[1-7]').multiply(0.0000275).add(-0.2)
        nir = optical.select('SR_B5')
        red = optical.select('SR_B4')
        ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
        ndvi_val = ndvi.sample(point, 30).first().get('NDVI').getInfo()
        if ndvi_val > 0.6:
            risk = 'high'
        elif ndvi_val > 0.3:
            risk = 'moderate'
        else:
            risk = 'low'
        return {'ndvi': round(ndvi_val, 4), 'vegetation_risk': risk, 'source': 'GEE'}
    except Exception as e:
        logging.error(f"GEE error: {e}")
        return {'ndvi': 0.45, 'vegetation_risk': 'moderate', 'source': 'error_fallback'}