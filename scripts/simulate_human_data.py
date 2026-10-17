"""Simulate the HUMAN layer for the demo:
- user reports per segment (unsafe / poorly_lit / isolated / harassment)
- partner venues (cafes, pharmacies that opted in as safe check-points)
- a context file (time, weather, events ending) consumed at request time

Run AFTER build_features (needs edges.parquet):
    python -m scripts.simulate_human_data
Then re-run build_features so the user-report columns get merged.

Everything is clearly labelled as simulated. Replace with real data when you have it.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

import pandas as pd
import geopandas as gpd

from scripts.config import PROCESSED_DIR, EDGES_PARQUET, POIS_PATH

random.seed(42)

REPORTS_CSV = PROCESSED_DIR / "user_reports.csv"
PARTNERS_JSON = PROCESSED_DIR / "partner_venues.json"
CONTEXT_JSON = PROCESSED_DIR / "context.json"
MOCK_USERS_JSON = PROCESSED_DIR / "mock_users.json"


def simulate_reports(n_reports: int = 150):
    """Weight reports toward segments that are dark, isolated or near parks."""
    edges = gpd.read_parquet(EDGES_PARQUET)
    weights = (
        (edges["lit_known"].fillna(False) & (edges["lit"] == 0)).astype(float) * 3
        + (edges["n_lively_open_23h"] == 0).astype(float) * 1.5
        + edges["risk_park_30m"].astype(float) * 2
        + edges["risk_tunnel_30m"].astype(float) * 2
        + (edges["dist_nearest_open_venue_23h_m"] > 300).astype(float) * 1.5
        + 0.1
    )
    sample = edges.sample(
        n=min(n_reports, len(edges)), weights=weights, replace=True)
    tags = ["unsafe", "poorly_lit", "isolated", "harassment"]
    tag_weights = [0.4, 0.3, 0.2, 0.1]
    comments = {
        "unsafe": ["Didn't feel safe at night", "Would avoid alone",
                   "Group of people hanging around"],
        "poorly_lit": ["Street lights broken", "Very dark stretch",
                       "No lighting between buildings"],
        "isolated": ["No one around", "Felt alone", "No open shops"],
        "harassment": ["Was catcalled here", "Felt watched",
                       "Unwanted attention"],
    }
    rows = []
    base_dt = datetime(2026, 10, 10, 22, 0)
    for _, e in sample.iterrows():
        tag = random.choices(tags, weights=tag_weights, k=1)[0]
        dt = base_dt + timedelta(days=random.randint(0, 7),
                                 hours=random.randint(0, 5),
                                 minutes=random.randint(0, 59))
        rows.append({
            "segment_id": e["segment_id"],
            "tag": tag,
            "comment": random.choice(comments[tag]),
            "reported_at": dt.isoformat(timespec="minutes"),
            "user_hash": f"anon_{random.randint(1000, 9999)}",
        })
    pd.DataFrame(rows).to_csv(REPORTS_CSV, index=False)
    print(f"[sim] {len(rows)} user reports -> {REPORTS_CSV}")


def simulate_partner_venues(n: int = 12):
    """Pick help / lively POIs and label them as partner safe check-points."""
    pois = gpd.read_parquet(POIS_PATH)
    candidates = pois[pois["category"].isin(["help", "lively"])]
    if len(candidates) == 0:
        PARTNERS_JSON.write_text("[]"); return
    picks = candidates.sample(n=min(n, len(candidates)), random_state=42)
    partners = []
    for _, p in picks.iterrows():
        partners.append({
            "name": p.get("name") or "Partner spot",
            "lat": float(p["lat"]),
            "lon": float(p["lon"]),
            "type": p.get("amenity") or p.get("shop") or "venue",
            "offers": random.choice([
                "safe wait inside", "call a friend", "free water",
                "walk-with-staff on request",
            ]),
            "hours": "08:00-02:00",
        })
    PARTNERS_JSON.write_text(json.dumps(partners, indent=2))
    print(f"[sim] {len(partners)} partner venues -> {PARTNERS_JSON}")


def write_context_sample():
    """Context the router/scorer reads at request time."""
    ctx = {
        "now": "2026-10-17T23:15:00-07:00",
        "weekday": "Friday",
        "hour": 23,
        "weather": {"condition": "clear", "temp_c": 14, "rain": False},
        "events_ending_soon": [
            {"name": "Cal Bears football", "venue": "California Memorial Stadium",
             "ends_at": "2026-10-17T23:30:00-07:00",
             "lat": 37.8707, "lon": -122.2510,
             "effect": "crowd dispersing nearby, extra foot traffic"},
        ],
        "notes": "Simulated for the hackathon demo.",
    }
    CONTEXT_JSON.write_text(json.dumps(ctx, indent=2))
    print(f"[sim] context -> {CONTEXT_JSON}")


def write_mock_users():
    users = [
        {"id": "u1", "name": "Léa",   "email_domain": "berkeley.edu",
         "gender": "f", "campus": "UCB", "pace_m_s": 1.3,
         "prefers_group_composition": "women_or_mixed", "languages": ["en", "fr"]},
        {"id": "u2", "name": "Sofia", "email_domain": "berkeley.edu",
         "gender": "f", "campus": "UCB", "pace_m_s": 1.4,
         "prefers_group_composition": "women_or_mixed", "languages": ["en", "es"]},
        {"id": "u3", "name": "Ravi",  "email_domain": "berkeley.edu",
         "gender": "m", "campus": "UCB", "pace_m_s": 1.5,
         "prefers_group_composition": "any", "languages": ["en", "hi"]},
        {"id": "u4", "name": "Maya",  "email_domain": "berkeley.edu",
         "gender": "nb", "campus": "UCB", "pace_m_s": 1.3,
         "prefers_group_composition": "any", "languages": ["en"]},
        {"id": "u5", "name": "Karim", "email_domain": "berkeley.edu",
         "gender": "m", "campus": "UCB", "pace_m_s": 0.9,
         "mobility": "wheelchair", "max_slope_pct": 5,
         "prefers_group_composition": "any", "languages": ["en", "ar"]},
        {"id": "u6", "name": "Priya", "email_domain": "berkeley.edu",
         "gender": "f", "campus": "UCB", "pace_m_s": 1.3,
         "prefers_group_composition": "women_or_mixed", "languages": ["en"]},
    ]
    MOCK_USERS_JSON.write_text(json.dumps(users, indent=2))
    print(f"[sim] {len(users)} mock users -> {MOCK_USERS_JSON}")


def main():
    simulate_reports()
    simulate_partner_venues()
    write_context_sample()
    write_mock_users()
    print("\nDone. Re-run `python -m scripts.build_features --force` so edges "
          "pick up user_reports and partner_venues columns.")


if __name__ == "__main__":
    main()
