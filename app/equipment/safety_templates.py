"""
safety_templates.py — Per-equipment-type pre-use safety checklists.

Keys are lowercase normalised versions of equipment.equipment_type.
Each value is an ordered list of 5 required item keys.
Each item must appear in the POST /equipment/<id>/safety-check request body
as {"checked": true, "note": ""} before the check is accepted.

To add a new equipment type: add its normalised name + 5-item list here.
The endpoint and template route pick this up with no other changes.
"""

SAFETY_CHECKLIST_TEMPLATES: dict[str, list[str]] = {
    "jetski": [
        "life_jackets_on_board",
        "engine_oil_level_checked",
        "fuel_level_ok",
        "kill_switch_lanyard_present",
        "guest_waiver_confirmed",
    ],
    "motorboat": [
        "life_jackets_on_board",
        "engine_oil_level_checked",
        "fuel_level_ok",
        "navigation_lights_working",
        "guest_waiver_confirmed",
    ],
    "paddle_boat": [
        "life_jackets_on_board",
        "hull_integrity_checked",
        "paddles_present",
        "drainage_plug_in_place",
        "guest_waiver_confirmed",
    ],
    "bicycle": [
        "brakes_working",
        "tires_inflated",
        "chain_lubricated",
        "seat_adjusted",
        "helmet_provided",
    ],
}


def get_template(equipment_type: str) -> list[str] | None:
    """Return the checklist for this equipment_type (case-insensitive), or None."""
    return SAFETY_CHECKLIST_TEMPLATES.get(equipment_type.strip().lower())
