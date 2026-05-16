# kml_generator.py
import simplekml
from datetime import datetime
import logging

def generate_damage_kml(damage_data, storm_name, output_path):
    """Create KML file with color‑coded poles for Google Earth."""
    kml = simplekml.Kml(name=f"{storm_name} - DTE Pole Damage Assessment")
    kml.document.description = (
        f"Post-storm damage assessment for DTE Energy.\n"
        f"Storm: {storm_name}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Total poles: {len(damage_data)}\n"
        f"High risk: {sum(1 for p in damage_data if p.get('risk_level')=='High')}\n"
        f"Est. repair cost: ${sum(p.get('estimated_repair_cost',0) for p in damage_data):,.0f}"
    )
    high = kml.newfolder(name="🔴 High Risk - Immediate")
    medium = kml.newfolder(name="🟠 Medium Risk - Schedule")
    low = kml.newfolder(name="🟢 Low Risk - Monitor")

    for pole in damage_data:
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
        p.coords = [(pole['longitude'], pole['latitude'])]
        p.style.iconstyle.color = color
        p.style.iconstyle.scale = scale
        p.description = f"""
        <![CDATA[
        <div style="font-family:Arial">
        <b>Pole {pole['pole_id']}</b><br>
        Risk Score: {pole.get('risk_score',0)}/100<br>
        Tilt: {pole.get('tilt_angle',0):.1f}°<br>
        Crack: {pole.get('crack_score',0):.1%}<br>
        Est. Cost: ${pole.get('estimated_repair_cost',0):,.0f}<br>
        Action: {pole.get('recommendation','Inspect')}
        </div>
        ]]>
        """
    kml.save(output_path)
    logging.info(f"KML saved to {output_path}")
    return output_path