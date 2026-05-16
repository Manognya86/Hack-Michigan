# kml_generator.py
import simplekml
from datetime import datetime

def generate_damage_kml(damage_data, storm_name, output_path):
    """Create a color-coded KML file for Google Earth."""
    kml = simplekml.Kml(name=f"{storm_name} - DTE Pole Damage Assessment")
    kml.document.description = f"Storm: {storm_name}\nDate: {datetime.now()}\nTotal poles: {len(damage_data)}"
    high = kml.newfolder(name="🔴 High Risk")
    medium = kml.newfolder(name="🟠 Medium Risk")
    low = kml.newfolder(name="🟢 Low Risk")

    for pole in damage_data:
        risk = pole.get('risk_level', 'Low')
        if risk == 'High':
            folder = high
            color = simplekml.Color.red
        elif risk == 'Medium':
            folder = medium
            color = simplekml.Color.orange
        else:
            folder = low
            color = simplekml.Color.green

        p = folder.newpoint(name=f"Pole {pole['pole_id']}")
        p.coords = [(pole['longitude'], pole['latitude'])]
        p.style.iconstyle.color = color
        p.style.iconstyle.scale = 1.0
        p.description = f"Risk: {pole.get('risk_score',0)}/100\nCost: ${pole.get('estimated_repair_cost',0)}"
    kml.save(output_path)
    return output_path