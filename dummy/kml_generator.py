# kml_generator.py
import logging
from datetime import datetime

try:
    import simplekml # type: ignore
    SIMPLEKML_AVAILABLE = True
except ImportError:
    SIMPLEKML_AVAILABLE = False
    logging.warning("simplekml not installed. KML generation disabled.")

def generate_damage_kml(damage_data, storm_name, output_path):
    """Create KML file with color‑coded poles for Google Earth."""
    if not SIMPLEKML_AVAILABLE:
        error_msg = "simplekml library is not installed. Please run: pip install simplekml"
        logging.error(error_msg)
        raise ImportError(error_msg)
    
    kml = simplekml.Kml(name=f"{storm_name} - DTE Pole Damage Assessment")
    kml.document.description = (
        f"Post-storm damage assessment for DTE Energy.\n"
        f"Storm: {storm_name}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Total poles: {len(damage_data)}\n"
        f"Est. repair cost: ${sum(p.get('estimated_repair_cost',0) for p in damage_data):,.0f}"
    )
    high = kml.newfolder(name="🔴 High Risk - Immediate")
    medium = kml.newfolder(name="🟠 Medium Risk - Schedule")
    low = kml.newfolder(name="🟢 Low Risk - Monitor")

    for pole in damage_data:
        lat = pole.get('latitude') or pole.get('lat')
        lon = pole.get('longitude') or pole.get('lng')
        if lat is None or lon is None:
            logging.warning(f"Skipping pole {pole.get('pole_id')}: missing coordinates")
            continue

        risk = pole.get('risk_level', 'Low')
        if risk == 'High':
            folder = high
            color = simplekml.Color.red
            scale = 1.2
        elif risk == 'Medium':
            folder = medium
            color = simplekml.Color.orange
            scale = 1.0
        else:
            folder = low
            color = simplekml.Color.green
            scale = 0.8

        p = folder.newpoint(name=f"Pole {pole['pole_id']}")
        p.coords = [(lon, lat)]
        p.style.iconstyle.color = color
        p.style.iconstyle.scale = scale
        p.description = f"""
        <![CDATA[
        <div style="font-family:Arial">
        <b>Pole {pole['pole_id']}</b><br>
        Damage Severity: {pole.get('predicted_damage_severity', 0)}<br>
        Failure Probability: {pole.get('failure_probability', 0):.0%}<br>
        Est. Cost: ${pole.get('estimated_repair_cost', 0):,.0f}<br>
        </div>
        ]]>
        """
    kml.save(output_path)
    logging.info(f"KML saved to {output_path}")
    return output_path