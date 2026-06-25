"""
test_menu.py — Menu category normalization + GET /menu/items/categories endpoint.

GAP 1 fix tests:
  1. Same category typed in different cases → only one entry in /categories
  2. /categories returns alphabetically sorted list
"""
import pytest
from app.extensions import db
from app.models.menu_item import MenuItem


def _create_item(client, manager_token, dept_id, name, category, price="500"):
    rv = client.post("/menu/items", json={
        "name": name,
        "price": price,
        "prep_station": "KITCHEN",
        "department_id": dept_id,
        "category": category,
    }, headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


def test_category_normalization_deduplicates(app, client, manager_token, general_dept_id):
    """
    POST two items with the same category typed in different cases.
    GET /menu/items/categories must return only one entry (title-cased).
    Root cause of GAP 1: "mains" vs "Mains" would appear as two separate sections
    on the waiter screen. Normalization prevents this silently.
    """
    _create_item(client, manager_token, general_dept_id, "Chips Masala", "mains")
    _create_item(client, manager_token, general_dept_id, "Nyama Choma",  "MAINS")

    rv = client.get("/menu/items/categories",
                    headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    categories = rv.get_json()["categories"]

    # Both items wrote "Mains" (title-cased) — only one distinct entry
    assert categories.count("Mains") == 1
    # No raw variants should leak through
    assert "mains" not in categories
    assert "MAINS" not in categories


def test_categories_returns_sorted_list(app, client, manager_token, general_dept_id):
    """
    GET /menu/items/categories returns categories in alphabetical order.
    The frontend needs this for consistent autocomplete dropdown ordering.
    """
    _create_item(client, manager_token, general_dept_id, "Tusker Bottle", "Beer",       "300")
    _create_item(client, manager_token, general_dept_id, "Grilled Fish",  "Mains",      "900")
    _create_item(client, manager_token, general_dept_id, "Fruit Salad",   "Appetizers", "400")

    rv = client.get("/menu/items/categories",
                    headers={"Authorization": f"Bearer {manager_token}"})
    assert rv.status_code == 200
    categories = rv.get_json()["categories"]

    # Must contain our three categories (seeded items may add more)
    for cat in ("Appetizers", "Beer", "Mains"):
        assert cat in categories

    # The list must be sorted ascending (check our slice is in order)
    our_cats = [c for c in categories if c in {"Appetizers", "Beer", "Mains"}]
    assert our_cats == sorted(our_cats)
    # Broader check: the full returned list is sorted
    assert categories == sorted(categories)
