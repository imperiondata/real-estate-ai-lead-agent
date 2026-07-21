"""Seed dummy inventory units + pricing rules for a client.

Usage:
    python seed_inventory.py --client-id 1
"""
from __future__ import annotations

import argparse

from database import SessionLocal
from models import InventoryUnit, PricingRule

UNITS = [
    {"project_name": "Serenity Towers", "tower": "A", "unit_code": "A-101", "bhk": "2BHK", "location": "Pune, Hinjewadi", "list_price": 8500000, "carpet_sqft": 950},
    {"project_name": "Serenity Towers", "tower": "A", "unit_code": "A-102", "bhk": "3BHK", "location": "Pune, Hinjewadi", "list_price": 12000000, "carpet_sqft": 1250},
    {"project_name": "Serenity Towers", "tower": "B", "unit_code": "B-201", "bhk": "2BHK", "location": "Pune, Hinjewadi", "list_price": 8700000, "carpet_sqft": 980},
    {"project_name": "Green Acres", "tower": "A", "unit_code": "GA-001", "bhk": "3BHK", "location": "Pune, Baner", "list_price": 15000000, "carpet_sqft": 1400},
    {"project_name": "Green Acres", "tower": "B", "unit_code": "GA-002", "bhk": "4BHK", "location": "Pune, Baner", "list_price": 22000000, "carpet_sqft": 1800},
    {"project_name": "Lake View Heights", "tower": "A", "unit_code": "LVH-101", "bhk": "1BHK", "location": "Mumbai, Andheri", "list_price": 5500000, "carpet_sqft": 600},
    {"project_name": "Lake View Heights", "tower": "A", "unit_code": "LVH-102", "bhk": "2BHK", "location": "Mumbai, Andheri", "list_price": 9000000, "carpet_sqft": 1000},
    {"project_name": "Lake View Heights", "tower": "B", "unit_code": "LVH-201", "bhk": "3BHK", "location": "Mumbai, Andheri", "list_price": 13500000, "carpet_sqft": 1350},
    {"project_name": "Skyline Residency", "tower": "A", "unit_code": "SR-01", "bhk": "2BHK", "location": "Bengaluru, Whitefield", "list_price": 7500000, "carpet_sqft": 900},
    {"project_name": "Skyline Residency", "tower": "A", "unit_code": "SR-02", "bhk": "3BHK", "location": "Bengaluru, Whitefield", "list_price": 11000000, "carpet_sqft": 1200},
    {"project_name": "Skyline Residency", "tower": "B", "unit_code": "SR-03", "bhk": "4BHK", "location": "Bengaluru, Whitefield", "list_price": 18000000, "carpet_sqft": 1600},
    {"project_name": "Sunrise Villas", "tower": "A", "unit_code": "SV-V01", "bhk": "3BHK", "location": "Hyderabad, Hitech City", "list_price": 14000000, "carpet_sqft": 1450},
    {"project_name": "Sunrise Villas", "tower": "A", "unit_code": "SV-V02", "bhk": "4BHK", "location": "Hyderabad, Hitech City", "list_price": 21000000, "carpet_sqft": 2000},
    {"project_name": "Royal Palm Estate", "tower": "A", "unit_code": "RPE-01", "bhk": "5BHK", "location": "Delhi, Dwarka", "list_price": 35000000, "carpet_sqft": 2800},
    {"project_name": "Royal Palm Estate", "tower": "B", "unit_code": "RPE-02", "bhk": "4BHK", "location": "Delhi, Dwarka", "list_price": 28000000, "carpet_sqft": 2200},
]

PRICING_RULES = [
    {"location": "Pune, Hinjewadi", "bhk": "2BHK", "min_budget": 7500000, "max_budget": 9000000, "list_price": 8500000},
    {"location": "Pune, Hinjewadi", "bhk": "3BHK", "min_budget": 10000000, "max_budget": 13000000, "list_price": 12000000},
    {"location": "Pune, Baner", "bhk": "3BHK", "min_budget": 13000000, "max_budget": 17000000, "list_price": 15000000},
    {"location": "Mumbai, Andheri", "bhk": "2BHK", "min_budget": 8000000, "max_budget": 10000000, "list_price": 9000000},
    {"location": "Bengaluru, Whitefield", "bhk": "3BHK", "min_budget": 9500000, "max_budget": 12500000, "list_price": 11000000},
]


def seed_inventory(client_id: int, clear: bool = False) -> None:
    db = SessionLocal()
    try:
        if clear:
            db.query(InventoryUnit).filter(InventoryUnit.client_id == client_id).delete()
            db.query(PricingRule).filter(PricingRule.client_id == client_id).delete()
            db.commit()

        for u in UNITS:
            exists = db.query(InventoryUnit).filter(
                InventoryUnit.client_id == client_id,
                InventoryUnit.unit_code == u["unit_code"],
            ).first()
            if not exists:
                db.add(InventoryUnit(client_id=client_id, **u))

        for r in PRICING_RULES:
            exists = db.query(PricingRule).filter(
                PricingRule.client_id == client_id,
                PricingRule.location == r["location"],
                PricingRule.bhk == r["bhk"],
            ).first()
            if not exists:
                db.add(PricingRule(client_id=client_id, **r))

        db.commit()
        total_units = db.query(InventoryUnit).filter(InventoryUnit.client_id == client_id).count()
        total_rules = db.query(PricingRule).filter(PricingRule.client_id == client_id).count()
        print(f"Seeded {total_units} inventory units + {total_rules} pricing rules for client {client_id}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed inventory + pricing data")
    parser.add_argument("--client-id", type=int, required=True)
    parser.add_argument("--clear", action="store_true", help="Clear existing data first")
    args = parser.parse_args()
    seed_inventory(args.client_id, clear=args.clear)
