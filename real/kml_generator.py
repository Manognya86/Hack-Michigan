# kml_generator.py
import simplekml
from datetime import datetime


def generate_damage_kml(damage_data: list, storm_name: str, output_path: str) -> str:
    """
    Create a color-coded KML for Google Earth.
    Includes risk score, cost estimate, and primary risk driver per pole.
    """
    kml = simplekml.Kml(name=f"{storm_name} — DTE GridWatch Pole Risk")
    kml.document.description = (
        f"Storm: {storm_name}\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Total poles: {len(damage_data)}\n"
        f"Source: GridWatch AI — Hack Michigan 2026"
    )

    folders = {
        'High':   (kml.newfolder(name="🔴 High Risk (Score ≥ 70)"),   simplekml.Color.red),
        'Medium': (kml.newfolder(name="🟠 Medium Risk (45–69)"),       simplekml.Color.orange),
        'Low':    (kml.newfolder(name="🟢 Low Risk (< 45)"),           simplekml.Color.green),
    }

    for pole in damage_data:
        level = pole.get('risk_level', 'Low')
        folder, color = folders.get(level, folders['Low'])

        p = folder.newpoint(name=f"Pole {pole['pole_id']}")
        p.coords = [(pole['longitude'], pole['latitude'])]
        p.style.iconstyle.color = color
        p.style.iconstyle.scale = 1.2 if level == 'High' else 1.0

        # Rich description includes SHAP primary reason when available
        primary = pole.get('primary_reason', 'N/A')
        p.description = (
            f"Risk Score: {pole.get('risk_score', 0)}/100\n"
            f"Risk Level: {level}\n"
            f"Est. Repair Cost: ${pole.get('estimated_repair_cost', 0):,.0f}\n"
            f"Age: {pole.get('age', 'N/A')} yrs\n"
            f"Material: {pole.get('material', 'N/A')}\n"
            f"Primary Driver: {primary}\n"
            f"Data Confidence: {pole.get('data_confidence', 'N/A')}"
        )

    kml.save(output_path)
    return output_path