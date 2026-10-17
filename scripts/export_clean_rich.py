"""Enriched 2-file export: data/clean_rich/points.csv + parks.geojson.

Covers all feature categories:
  Visibility, Lively, Help, Risk, Crime, Accessibility, Human layer.
Context (time, weather, events) stays in context.json (not geographic).
"""
from __future__ import annotations

import json
import shutil

import pandas as pd
import geopandas as gpd
import osmnx as ox

from scripts.config import (
    CENTER, RADIUS_M, PROCESSED_DIR, POIS_PATH, EDGES_PARQUET, RAW_DIR,
)

RICH_DIR = PROCESSED_DIR.parent / "clean_rich"
RICH_DIR.mkdir(parents=True, exist_ok=True)
POINTS_CSV = RICH_DIR / "points.csv"
PARKS_GEOJSON = RICH_DIR / "parks.geojson"
CONTEXT_COPY = RICH_DIR / "context.json"

COLS = [
    "lat", "lon", "kind", "hour",
    "name", "subtype", "source",
    "open_now_14h", "open_now_23h", "hours_known",
    "severity", "crime_type", "osm_id",
    "segment_id", "length_m", "lit", "lit_known", "width_m", "width_known",
    "sidewalk", "surface", "steps", "slope_pct", "slope_known",
    "dead_end", "isolation_m",
    "n_cameras_50m", "n_benches_30m", "n_rest_points_50m", "n_kerbs_20m",
    "n_lively_open_14h", "n_lively_open_23h",
    "n_transit_100m", "n_night_departures_100m",
    "dist_help_open_23h_m",
    "incidents_day", "incidents_evening", "incidents_night",
    "risk_park_30m", "risk_tunnel_30m", "risk_parking_30m",
    "risk_construction_30m", "n_partner_venues_50m",
    "reports_unsafe", "reports_poorly_lit", "reports_isolated", "reports_harassment",
    "trip_id", "user_id", "rating_safety", "rating_isolation",
    "rating_dignity", "rating_overall", "comment", "duration_min",
]


def _row(**kw):
    r = {c: "" for c in COLS}
    r.update(kw)
    return r


def _poi_rows(pois):
    rows = []
    for _, r in pois[pois["category"] == "help"].iterrows():
        rows.append(_row(lat=r["lat"], lon=r["lon"], kind="help",
            name=r.get("name") or "",
            subtype=(r.get("amenity") or r.get("shop") or r.get("emergency") or "help"),
            source="OSM",
            open_now_14h=bool(r.get("open_14h", False)),
            open_now_23h=bool(r.get("open_23h", False)),
            hours_known=bool(r.get("hours_known", False))))
    for _, r in pois[pois["category"] == "lively"].iterrows():
        k = "venue_late" if r.get("open_23h") else "venue"
        rows.append(_row(lat=r["lat"], lon=r["lon"], kind=k,
            name=r.get("name") or "",
            subtype=(r.get("amenity") or r.get("shop") or "venue"),
            source="OSM",
            open_now_14h=bool(r.get("open_14h", False)),
            open_now_23h=bool(r.get("open_23h", False)),
            hours_known=bool(r.get("hours_known", False))))
    for _, r in pois[pois["category"] == "transit"].iterrows():
        rows.append(_row(lat=r["lat"], lon=r["lon"], kind="transit",
            name=r.get("name") or "",
            subtype=(r.get("railway") or r.get("highway")
                     or r.get("public_transport") or "stop"),
            source="OSM"))
    for _, r in pois[pois["category"] == "surveillance"].iterrows():
        rows.append(_row(lat=r["lat"], lon=r["lon"], kind="camera",
            subtype=str(r.get("man_made") or ""), source="OSM"))
    for _, r in pois[pois["category"] == "risk"].iterrows():
        sub = (r.get("leisure") or r.get("amenity") or r.get("landuse")
               or ("tunnel" if r.get("tunnel") else ""))
        kind = "park_centroid" if sub == "park" else (str(sub) if sub else "risk")
        rows.append(_row(lat=r["lat"], lon=r["lon"], kind=kind,
            name=r.get("name") or "", source="OSM"))
    if (pois["category"] == "accessibility").any():
        acc = pois[pois["category"] == "accessibility"]
        for _, r in acc.iterrows():
            am = r.get("amenity") if "amenity" in acc.columns else None
            kb = r.get("kerb") if "kerb" in acc.columns else None
            if am == "bench":
                rows.append(_row(lat=r["lat"], lon=r["lon"], kind="bench", source="OSM"))
            elif am in ("drinking_water", "toilets"):
                rows.append(_row(lat=r["lat"], lon=r["lon"], kind="rest_point",
                                 subtype=str(am), source="OSM"))
            elif kb:
                rows.append(_row(lat=r["lat"], lon=r["lon"], kind="kerb",
                                 subtype=str(kb), source="OSM"))
    return rows


def _lamp_rows():
    rows = []
    try:
        lamps = ox.features_from_point(CENTER, tags={"highway": "street_lamp"},
                                       dist=RADIUS_M)
        if lamps is not None and len(lamps):
            lamps = lamps.reset_index()
            lamps["geom_pt"] = lamps.geometry.apply(
                lambda g: g if g.geom_type == "Point" else g.centroid)
            for _, r in lamps.iterrows():
                p = r["geom_pt"]
                rows.append(_row(lat=p.y, lon=p.x, kind="lamp",
                                 subtype="street_lamp", source="OSM",
                                 osm_id=str(r.get("osmid", ""))))
    except Exception as e:
        print(f"[lamps] skipped: {e}")
    return rows


def _outage_rows():
    import random
    rows = []
    o = RAW_DIR / "light_outages.csv"
    if o.exists():
        for _, r in pd.read_csv(o).iterrows():
            rows.append(_row(lat=r["lat"], lon=r["lon"], kind="light_outage",
                             source="city_open_data",
                             severity=r.get("severity", "")))
    else:
        random.seed(1)
        pois = gpd.read_parquet(POIS_PATH)
        parks = pois[(pois["category"] == "risk") &
                     (pois["leisure"].astype(str) == "park")]
        if len(parks):
            for _, p in parks.sample(n=min(15, len(parks)), random_state=1,
                                     replace=len(parks) < 15).iterrows():
                rows.append(_row(
                    lat=float(p["lat"]) + random.uniform(-0.001, 0.001),
                    lon=float(p["lon"]) + random.uniform(-0.001, 0.001),
                    kind="light_outage", source="simulated",
                    severity=random.choice(["low", "medium", "high"])))
    return rows


def _crime_rows():
    import random
    rows = []
    i = RAW_DIR / "incidents.csv"
    if i.exists():
        df = pd.read_csv(i)
        df["dt"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["lat", "lon", "dt"])
        for _, r in df.iterrows():
            rows.append(_row(lat=r["lat"], lon=r["lon"], kind="crime",
                             hour=int(r["dt"].hour), source="city_open_data",
                             crime_type=str(r.get("type", "")),
                             severity=str(r.get("severity", ""))))
    else:
        random.seed(2)
        types = ["theft", "assault", "harassment", "burglary", "robbery"]
        for _ in range(60):
            rows.append(_row(
                lat=CENTER[0] + random.uniform(-0.015, 0.015),
                lon=CENTER[1] + random.uniform(-0.015, 0.015),
                kind="crime",
                hour=random.choices(range(24),
                                    weights=[1]*7 + [2]*12 + [5]*5)[0],
                source="simulated",
                crime_type=random.choice(types),
                severity=random.choice(["low", "medium", "high"])))
    return rows


def _partner_rows():
    rows = []
    p = PROCESSED_DIR / "partner_venues.json"
    if not p.exists(): return rows
    for v in json.loads(p.read_text()):
        rows.append(_row(lat=v["lat"], lon=v["lon"], kind="partner",
            name=v.get("name", ""), subtype=v.get("type", ""),
            source="partnership", open_now_23h=True, hours_known=True,
            comment=v.get("offers", "")))
    return rows


def _user_report_rows(edges):
    rows = []
    rc = PROCESSED_DIR / "user_reports.csv"
    if not rc.exists(): return rows
    df = pd.read_csv(rc)
    mid = edges.set_index("segment_id").geometry.apply(
        lambda g: g.interpolate(0.5, normalized=True))
    for _, r in df.iterrows():
        g = mid.get(r["segment_id"])
        if g is None: continue
        rows.append(_row(lat=g.y, lon=g.x, kind="user_report",
            subtype=r["tag"], source="user",
            comment=str(r.get("comment", ""))))
    return rows


def _trip_rating_rows(edges):
    rows = []
    tr = PROCESSED_DIR / "trip_ratings.csv"
    if not tr.exists(): return rows
    df = pd.read_csv(tr)
    mid = edges.set_index("segment_id").geometry.apply(
        lambda g: g.interpolate(0.5, normalized=True))
    for _, r in df.iterrows():
        sids = str(r["segment_ids"]).split("|")
        for pos, sid in [("start", sids[0]), ("end", sids[-1])]:
            g = mid.get(sid)
            if g is None: continue
            rows.append(_row(lat=g.y, lon=g.x, kind="trip_rating_endpoint",
                subtype=pos, source="user",
                trip_id=r["trip_id"], user_id=r["user_id"],
                rating_safety=r["rating_safety"],
                rating_isolation=r["rating_isolation"],
                rating_dignity=r["rating_dignity"],
                rating_overall=r["rating_overall"],
                comment=str(r.get("comment", "")),
                duration_min=r.get("duration_min", "")))
    return rows


def _street_segment_rows(edges):
    rows = []
    for _, e in edges.iterrows():
        if e.geometry is None or e.geometry.is_empty: continue
        mid = e.geometry.interpolate(0.5, normalized=True)
        rows.append(_row(lat=mid.y, lon=mid.x, kind="street_segment",
            name=str(e.get("name") or ""), source="OSM",
            segment_id=str(e["segment_id"]),
            length_m=float(e.get("length_m", 0)),
            lit=e.get("lit"), lit_known=bool(e.get("lit_known", False)),
            width_m=e.get("width_m"),
            width_known=bool(e.get("width_known", False)),
            sidewalk=str(e.get("sidewalk") or ""),
            surface=str(e.get("surface") or ""),
            steps=bool(e.get("steps", False)),
            slope_pct=e.get("slope_pct", ""),
            slope_known=e.get("slope_known", ""),
            dead_end=bool(e.get("dead_end", False)),
            isolation_m=e.get("dist_nearest_open_venue_23h_m", ""),
            n_cameras_50m=int(e.get("n_cameras_50m", 0) or 0),
            n_benches_30m=int(e.get("n_benches_30m", 0) or 0),
            n_rest_points_50m=int(e.get("n_rest_points_50m", 0) or 0),
            n_kerbs_20m=int(e.get("n_kerbs_20m", 0) or 0),
            n_lively_open_14h=int(e.get("n_lively_open_14h", 0) or 0),
            n_lively_open_23h=int(e.get("n_lively_open_23h", 0) or 0),
            n_transit_100m=int(e.get("n_transit_100m", 0) or 0),
            n_night_departures_100m=e.get("n_night_departures_100m", 0),
            dist_help_open_23h_m=float(e.get("dist_help_open_23h_m", 0) or 0),
            incidents_day=e.get("incidents_day", 0),
            incidents_evening=e.get("incidents_evening", 0),
            incidents_night=e.get("incidents_night", 0),
            risk_park_30m=bool(e.get("risk_park_30m", False)),
            risk_tunnel_30m=bool(e.get("risk_tunnel_30m", False)),
            risk_parking_30m=bool(e.get("risk_parking_30m", False)),
            risk_construction_30m=bool(e.get("risk_construction_30m", False)),
            n_partner_venues_50m=int(e.get("n_partner_venues_50m", 0) or 0),
            reports_unsafe=int(e.get("reports_unsafe", 0) or 0),
            reports_poorly_lit=int(e.get("reports_poorly_lit", 0) or 0),
            reports_isolated=int(e.get("reports_isolated", 0) or 0),
            reports_harassment=int(e.get("reports_harassment", 0) or 0),
        ))
    return rows


def export_parks():
    try:
        parks = ox.features_from_point(CENTER, tags={"leisure": "park"},
                                       dist=RADIUS_M)
    except Exception as e:
        print(f"[parks] download failed: {e}")
        return
    if parks is None or len(parks) == 0: return
    parks = parks.reset_index()
    parks = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    for c in ["name", "leisure", "lit", "access", "opening_hours",
              "wheelchair", "surface"]:
        if c not in parks.columns: parks[c] = None
    parks["area_m2"] = parks.to_crs("EPSG:32610").geometry.area.round(1)
    for c in parks.columns:
        if c == "geometry": continue
        parks[c] = parks[c].apply(
            lambda v: ";".join(map(str, v)) if isinstance(v, list) else v)
    keep = ["name", "leisure", "lit", "access", "opening_hours",
            "wheelchair", "surface", "area_m2", "geometry"]
    gpd.GeoDataFrame(parks[keep], geometry="geometry",
                     crs=parks.crs).to_file(PARKS_GEOJSON, driver="GeoJSON")
    print(f"[parks] {len(parks)} polygons -> {PARKS_GEOJSON}")


README = """# data/clean_rich — enriched view (2-file format)
points.csv (lat, lon, kind, hour, + many extra columns)
parks.geojson (polygons)
context.json (non-geographic context)

Reported crime is BIASED by reporting and patrolling: weight LOW and never
present as 'dangerous areas'.
"""


def main():
    pois = gpd.read_parquet(POIS_PATH)
    edges = gpd.read_parquet(EDGES_PARQUET)
    rows = []
    rows += _poi_rows(pois)
    rows += _lamp_rows()
    rows += _outage_rows()
    rows += _crime_rows()
    rows += _partner_rows()
    rows += _user_report_rows(edges)
    rows += _trip_rating_rows(edges)
    rows += _street_segment_rows(edges)
    df = pd.DataFrame(rows, columns=COLS)
    df.to_csv(POINTS_CSV, index=False)
    print(f"[rich] {len(df)} rows -> {POINTS_CSV}")
    print(df["kind"].value_counts().to_string())
    export_parks()
    ctx = PROCESSED_DIR / "context.json"
    if ctx.exists(): shutil.copy(ctx, CONTEXT_COPY)
    (RICH_DIR / "README.md").write_text(README)
    print("\nRich clean export ready in data/clean_rich/")


if __name__ == "__main__":
    main()
