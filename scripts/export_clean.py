"""Export the data layer to the format requested by teammates, enriched.

Required columns (first, in this order):
    data/clean/points.csv  : lat, lon, kind, hour
      kind in {crime, light_outage, lamp, venue_late, help}
      hour set only for kind='crime' (0-23)
    data/clean/parks.geojson : park polygons

Extra columns kept so the scorer/router have the richness we already have
(all empty when not applicable):
    name, subtype, source, open_now_23h, hours_known, severity,
    crime_type, osm_id

The raw files (graph.graphml, edges.parquet, pois.parquet, reports, partners,
context, mock users) are NOT replaced. This is a VIEW on top of them.

Run after build_features (and optionally enrich_features + simulate_human_data):
    python -m scripts.export_clean
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import geopandas as gpd
import osmnx as ox

from scripts.config import (
    CENTER, RADIUS_M, PROCESSED_DIR, POIS_PATH, RAW_DIR,
)

CLEAN_DIR = PROCESSED_DIR.parent / "clean"
CLEAN_DIR.mkdir(parents=True, exist_ok=True)
POINTS_CSV = CLEAN_DIR / "points.csv"
PARKS_GEOJSON = CLEAN_DIR / "parks.geojson"


# ---- POINTS ----------------------------------------------------------------

EXTRA_COLS = ["name", "subtype", "source", "open_now_23h", "hours_known",
              "severity", "crime_type", "osm_id"]


def _row(lat, lon, kind, hour="", **extras):
    row = {"lat": float(lat), "lon": float(lon), "kind": kind, "hour": hour}
    for c in EXTRA_COLS:
        row[c] = extras.get(c, "")
    return row


def _lamp_and_outage_rows() -> list[dict]:
    rows = []
    try:
        lamps = ox.features_from_point(
            CENTER, tags={"highway": "street_lamp"}, dist=RADIUS_M)
        if lamps is not None and len(lamps):
            lamps = lamps.reset_index()
            lamps["geom_pt"] = lamps.geometry.apply(
                lambda g: g if g.geom_type == "Point" else g.centroid)
            for _, r in lamps.iterrows():
                p = r["geom_pt"]
                rows.append(_row(p.y, p.x, "lamp",
                                 subtype="street_lamp", source="OSM",
                                 osm_id=str(r.get("osmid", ""))))
    except Exception as e:
        print(f"[lamps] skipped: {e}")

    outages_csv = RAW_DIR / "light_outages.csv"
    if outages_csv.exists():
        df = pd.read_csv(outages_csv)
        for _, r in df.iterrows():
            rows.append(_row(r["lat"], r["lon"], "light_outage",
                             subtype=r.get("status", "reported"),
                             source="city_open_data",
                             severity=r.get("severity", "")))
    else:
        import random
        random.seed(1)
        pois = gpd.read_parquet(POIS_PATH)
        parks = pois[(pois["category"] == "risk") &
                     (pois["leisure"].astype(str) == "park")]
        if len(parks) > 0:
            for _, p in parks.sample(n=min(15, len(parks)), random_state=1,
                                     replace=len(parks) < 15).iterrows():
                rows.append(_row(
                    float(p["lat"]) + random.uniform(-0.001, 0.001),
                    float(p["lon"]) + random.uniform(-0.001, 0.001),
                    "light_outage",
                    subtype="simulated_outage", source="simulated",
                    severity=random.choice(["low", "medium", "high"])))
        print("[outages] simulated (no light_outages.csv)")
    return rows


def _venue_late_rows(pois: gpd.GeoDataFrame) -> list[dict]:
    sub = pois[(pois["category"] == "lively") & pois["open_23h"].fillna(False)]
    rows = []
    for _, r in sub.iterrows():
        rows.append(_row(
            r["lat"], r["lon"], "venue_late",
            name=r.get("name") or "",
            subtype=(r.get("amenity") or r.get("shop") or "venue"),
            source="OSM",
            open_now_23h=True,
            hours_known=bool(r.get("hours_known", False)),
        ))
    return rows


def _help_rows(pois: gpd.GeoDataFrame) -> list[dict]:
    sub = pois[pois["category"] == "help"]
    rows = []
    for _, r in sub.iterrows():
        rows.append(_row(
            r["lat"], r["lon"], "help",
            name=r.get("name") or "",
            subtype=(r.get("amenity") or r.get("shop")
                     or r.get("emergency") or "help"),
            source="OSM",
            open_now_23h=bool(r.get("open_23h", False)),
            hours_known=bool(r.get("hours_known", False)),
        ))
    return rows


def _crime_rows() -> list[dict]:
    incidents = RAW_DIR / "incidents.csv"
    rows = []
    if incidents.exists():
        df = pd.read_csv(incidents)
        df["dt"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["lat", "lon", "dt"])
        for _, r in df.iterrows():
            rows.append(_row(
                r["lat"], r["lon"], "crime", hour=int(r["dt"].hour),
                source="city_open_data",
                crime_type=str(r.get("type", "")),
                severity=str(r.get("severity", ""))))
        print(f"[crime] loaded {len(rows)} real incidents")
    else:
        import random
        random.seed(2)
        types = ["theft", "assault", "harassment", "burglary", "robbery"]
        for _ in range(60):
            rows.append(_row(
                CENTER[0] + random.uniform(-0.015, 0.015),
                CENTER[1] + random.uniform(-0.015, 0.015),
                "crime",
                hour=random.choices(range(24),
                                    weights=[1]*7 + [2]*12 + [5]*5)[0],
                source="simulated",
                crime_type=random.choice(types),
                severity=random.choice(["low", "medium", "high"])))
        print("[crime] simulated 60 incidents (no incidents.csv found)")
    return rows


def export_points():
    pois = gpd.read_parquet(POIS_PATH)
    rows = []
    rows += _lamp_and_outage_rows()
    rows += _venue_late_rows(pois)
    rows += _help_rows(pois)
    rows += _crime_rows()
    cols = ["lat", "lon", "kind", "hour"] + EXTRA_COLS
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(POINTS_CSV, index=False)
    print(f"[points] {len(df)} rows -> {POINTS_CSV}")
    print(df["kind"].value_counts().to_string())


# ---- PARKS -----------------------------------------------------------------

def export_parks():
    try:
        parks = ox.features_from_point(
            CENTER, tags={"leisure": "park"}, dist=RADIUS_M)
    except Exception as e:
        print(f"[parks] download failed: {e}")
        return
    if parks is None or len(parks) == 0:
        print("[parks] no parks found"); return
    parks = parks.reset_index()
    # Keep polygons only (drop Point entries)
    parks = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    # Enrich with a few optional attributes if present in OSM
    for c in ["name", "leisure", "lit", "access", "opening_hours",
              "wheelchair", "surface"]:
        if c not in parks.columns:
            parks[c] = None
    parks["area_m2"] = parks.to_crs("EPSG:32610").geometry.area.round(1)
    keep = ["name", "leisure", "lit", "access", "opening_hours",
            "wheelchair", "surface", "area_m2", "geometry"]
    gpd.GeoDataFrame(parks[keep], geometry="geometry",
                     crs=parks.crs).to_file(PARKS_GEOJSON, driver="GeoJSON")
    print(f"[parks] {len(parks)} polygons -> {PARKS_GEOJSON}")


README_TEXT = """# data/clean — simplified view

## points.csv
Required columns (always present, in this order):
  lat, lon, kind, hour
  - kind in {crime, light_outage, lamp, venue_late, help}
  - hour in [0, 23] when kind='crime', else empty

Extra columns (empty when not applicable):
  name           POI name when known (venue_late, help)
  subtype        OSM amenity/shop/emergency/leisure (e.g. "pharmacy", "bar")
  source         OSM | city_open_data | simulated
  open_now_23h   bool, for venue_late / help
  hours_known    bool, True if OSM opening_hours parsed
  severity       low | medium | high (crime, light_outage)
  crime_type     theft | assault | harassment | burglary | robbery
  osm_id         OSM id when available

Reported crime is biased by reporting and patrolling: weight it LOW and
present it as "reported incidents", never as "danger".

## parks.geojson
Polygons of parks (OSM leisure=park), with: name, leisure, lit, access,
opening_hours, wheelchair, surface, area_m2.

## Richer source files (do not duplicate here)
- data/processed/graph.graphml           street network graph
- data/processed/edges.parquet           all per-edge features (lit, width,
                                         sidewalk, risks, benches, kerbs,
                                         help distance, user reports, ...)
- data/processed/pois.parquet            all POIs with opening hours
- data/processed/user_reports.csv        simulated user reports
- data/processed/partner_venues.json     simulated partner safe spots
- data/processed/context.json            time / weather / events context
- data/processed/mock_users.json         6 mock users for matching
"""


def main():
    export_points()
    export_parks()
    (CLEAN_DIR / "README.md").write_text(README_TEXT)
    print("\nClean export ready in data/clean/")


if __name__ == "__main__":
    main()
