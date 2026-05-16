# gee_utils.py
import logging

GEE_AVAILABLE = False
try:
    import ee
    ee.Initialize()
    GEE_AVAILABLE = True
    logging.info("Google Earth Engine initialized.")
except Exception:
    logging.warning("GEE not available — will use fallback NDVI values.")


def get_ndvi(lat: float, lon: float) -> dict:
    """
    Return NDVI and vegetation risk for a location.
    Uses Landsat 8 via Google Earth Engine when available;
    falls back to mock values designed for SE Michigan.
    """
    if not GEE_AVAILABLE:
        return _mock_ndvi(lat, lon)

    try:
        import ee
        point = ee.Geometry.Point(lon, lat)
        collection = (
            ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
            .filterBounds(point)
            .filterDate('2024-01-01', '2025-12-31')
            .sort('CLOUD_COVER')
        )
        image = collection.first()
        if image is None:
            return {'ndvi': None, 'vegetation_risk': 'unknown', 'source': 'no_imagery'}

        nir  = image.select('SR_B5').multiply(0.0000275).add(-0.2)
        red  = image.select('SR_B4').multiply(0.0000275).add(-0.2)
        ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
        ndvi_val = ndvi.sample(point, 30).first().get('NDVI').getInfo()

        risk = 'high' if ndvi_val > 0.6 else 'moderate' if ndvi_val > 0.3 else 'low'
        return {'ndvi': round(float(ndvi_val), 4), 'vegetation_risk': risk, 'source': 'GEE'}

    except Exception as e:
        logging.error(f"GEE NDVI error: {e}")
        return _mock_ndvi(lat, lon)


def _mock_ndvi(lat: float, lon: float) -> dict:
    """
    Deterministic mock NDVI based on rough SE Michigan vegetation patterns.
    Higher NDVI in suburban/wooded areas (west Oakland, Washtenaw),
    lower in urban core (Detroit, Hamtramck).
    """
    # Simple proxy: distance from urban core
    dist_from_core = abs(lat - 42.33) + abs(lon + 83.05)
    ndvi = round(0.25 + dist_from_core * 0.8, 3)
    ndvi = min(max(ndvi, 0.15), 0.75)
    risk = 'high' if ndvi > 0.55 else 'moderate' if ndvi > 0.35 else 'low'
    return {'ndvi': ndvi, 'vegetation_risk': risk, 'source': 'mock_spatial'}