"""Download POIs and compute RAW features per street segment.

Run from repo root (after build_graph):
    python -m scripts.build_features

NO scoring, NO normalization. Unknown stays NaN with a *_known flag.
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import osmnx as ox

from scripts.config import (
    CENTER,
    RADIUS_M,
    METRIC_CRS,
    GRAPH_PATH,
    POIS_PATH,
    EDGES_PARQUET,
    EDGES_GEOJSON,
    PROCESSED_DIR,
)

warnings.filterwarnings("ignore")

# ---------- POI download -----------------------------------------------------

POI_TAG_SETS = {
    "lively": {
        "amenity": ["bar", "pub", "restaurant", "cafe", "fast_food", "nightclub"],
        "shop": True,
    },
    "help": {
        "amenity": ["police", "fire_station", "hospital", "clinic", "doctors",
                    "pharmacy", "shelter", "fuel"],
        "emergency": ["phone"],
        "shop": ["convenience"],
    },
    "transit": {
        "highway": ["bus_stop"],
        "railway": ["station", "subway_entrance"],
        "public_transport": True,
    },
    "surveillance": {"man_made": ["surveillance"]},
    "risk": {
        "leisure": ["park"],
        "tunnel": True,
        "amenity": ["parking"],
        "landuse": ["construction"],
    },
    "accessibility": {
        "amenity": ["bench", "drinking_water", "toilets"],
        "kerb": True,          # OSM kerb nodes (lowered, flush, raised, …)
        "wheelchair": True,
    },
}


def _to_point(geom):
    if geom is None:
        return None
    if geom.geom_type == "Point":
        return geom
    try:
        return geom.centroid
    except Exception:
        return None


def download_pois() -> gpd.GeoDataFrame:
    all_rows = []
    for category, tags in POI_TAG_SETS.items():
        print(f"[pois] Fetching category={category} ...")
        try:
            gdf = ox.features_from_point(CENTER, tags=tags, dist=RADIUS_M)
        except Exception as e:
            print(f"[pois] WARN category={category}: {e}")
            continue
        if gdf is None or len(gdf) == 0:
            print(f"[pois] category={category}: 0 features")
            continue
        gdf = gdf.reset_index()
        gdf["category"] = category
        gdf["geometry_pt"] = gdf.geometry.apply(_to_point)
        gdf = gdf[gdf["geometry_pt"].notna()].copy()
        gdf = gpd.GeoDataFrame(gdf.drop(columns=["geometry"]),
                               geometry="geometry_pt", crs=gdf.crs)
        keep_cols = ["category", "name", "amenity", "shop", "highway",
                     "railway", "public_transport", "man_made", "leisure",
                     "tunnel", "landuse", "emergency", "opening_hours",
                     "kerb", "wheelchair"]
        for c in keep_cols:
            if c not in gdf.columns:
                gdf[c] = pd.NA
        gdf["lon"] = gdf.geometry.x
        gdf["lat"] = gdf.geometry.y
        all_rows.append(gdf[keep_cols + ["lon", "lat", "geometry_pt"]].rename(
            columns={"geometry_pt": "geometry"}))
        print(f"[pois] category={category}: {len(gdf)} features")

    if not all_rows:
        raise RuntimeError("No POIs downloaded; aborting.")

    pois = gpd.GeoDataFrame(pd.concat(all_rows, ignore_index=True),
                            geometry="geometry", crs="EPSG:4326")
    pois = _flatten_lists(pois)
    return pois


def _flatten_lists(gdf):
    """Convert any list-valued cell to a ';'-joined string so pyarrow can
    serialize the DataFrame to parquet. OSM often returns lists for name,
    highway, surface, etc. when a feature has several tagged values."""
    for col in gdf.columns:
        if col == "geometry":
            continue
        gdf[col] = gdf[col].apply(
            lambda v: ";".join(map(str, v)) if isinstance(v, list) else v)
    return gdf


# ---------- Opening hours ----------------------------------------------------

# Try multiple OSM opening-hours parsers; fall back to heuristic if none.
_OH_PARSER = None
try:
    from opening_hours import OpeningHours as _OH  # opening_hours_py
    def _parse_oh(s, dt):
        return _OH(s).is_open(dt)
    _OH_PARSER = "opening_hours_py"
except Exception:
    try:
        from humanized_opening_hours import OHParser  # type: ignore
        def _parse_oh(s, dt):
            return OHParser(s).is_open(dt)
        _OH_PARSER = "humanized_opening_hours"
    except Exception:
        def _parse_oh(s, dt):
            raise RuntimeError("no OH parser")

_NIGHT_HEURISTIC = {
    "bar": 2, "pub": 2, "nightclub": 2,
    "restaurant": 22, "fast_food": 23,
    "convenience": 23, "fuel": 23,
    "cafe": 20,
}


def _closes_hour_heuristic(amenity: Any, shop: Any) -> int | None:
    for key in (amenity, shop):
        if isinstance(key, str) and key in _NIGHT_HEURISTIC:
            return _NIGHT_HEURISTIC[key]
    return None


def is_open(opening_hours: Any, amenity: Any, shop: Any,
            hour: int, weekday: int) -> tuple[bool, bool]:
    """Return (is_open, hours_known)."""
    if isinstance(opening_hours, str) and opening_hours.strip() and _OH_PARSER:
        try:
            now = datetime(2026, 10, 19)  # a Monday
            days_ahead = (weekday - now.weekday()) % 7
            dt = now.replace(hour=hour, minute=0, second=0) + \
                 pd.Timedelta(days=days_ahead)
            return bool(_parse_oh(opening_hours, dt)), True
        except Exception:
            pass
    closes = _closes_hour_heuristic(amenity, shop)
    if closes is None:
        return (6 <= hour <= 19, False)  # default: day only
    # Open from ~8 AM to `closes` (closes==2 means 2 AM next day)
    if closes >= 24 or closes <= 5:
        open_now = (hour >= 8) or (hour < closes)
    else:
        open_now = 8 <= hour < closes
    return open_now, False


def tag_opening_hours(pois: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out14, out23, known = [], [], []
    for _, r in pois.iterrows():
        o14, k14 = is_open(r.get("opening_hours"), r.get("amenity"),
                           r.get("shop"), 14, 1)
        o23, k23 = is_open(r.get("opening_hours"), r.get("amenity"),
                           r.get("shop"), 23, 5)  # Fri night
        out14.append(o14); out23.append(o23); known.append(k14 or k23)
    pois["open_14h"] = out14
    pois["open_23h"] = out23
    pois["hours_known"] = known
    return pois


# ---------- Edge features ----------------------------------------------------

def _lit_to_num(v: Any) -> tuple[float, bool]:
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("yes", "24/7"): return 1.0, True
        if s == "no": return 0.0, True
    return np.nan, False


_WIDTH_BY_HWY = {
    "footway": 2.0, "path": 1.5, "pedestrian": 4.0, "steps": 1.5,
    "residential": 5.5, "service": 4.0, "tertiary": 7.0,
    "secondary": 9.0, "primary": 11.0, "cycleway": 2.0,
}


def _parse_width(v: Any, highway: Any) -> tuple[float, bool]:
    try:
        if isinstance(v, list): v = v[0]
        return float(v), True
    except Exception:
        pass
    hwy = highway[0] if isinstance(highway, list) else highway
    return _WIDTH_BY_HWY.get(hwy, np.nan), False


def _sidewalk(v: Any) -> str:
    if isinstance(v, list): v = v[0]
    if isinstance(v, str) and v.lower() in ("yes", "both", "left", "right", "separate"):
        return "yes"
    if isinstance(v, str) and v.lower() == "no":
        return "no"
    return "unknown"


def compute_edge_features(G, pois: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print("[edges] Converting graph to GeoDataFrame ...")
    edges = ox.graph_to_gdfs(G, nodes=False)
    edges = edges.reset_index()  # columns u, v, key
    edges["segment_id"] = (edges["u"].astype(str) + "_" +
                           edges["v"].astype(str) + "_" +
                           edges["key"].astype(str))

    print("[edges] Projecting to metric CRS ...")
    edges_m = edges.to_crs(METRIC_CRS)
    pois_m = pois.to_crs(METRIC_CRS)

    # Base attributes
    lit_num, lit_known = zip(*edges["lit"].map(_lit_to_num)) \
        if "lit" in edges.columns else ([np.nan]*len(edges), [False]*len(edges))
    edges["lit"] = list(lit_num)
    edges["lit_known"] = list(lit_known)

    hwy_series = edges["highway"] if "highway" in edges.columns else [None]*len(edges)
    width_vals, width_known = [], []
    width_src = edges["width"] if "width" in edges.columns else [None]*len(edges)
    for w, h in zip(width_src, hwy_series):
        wv, wk = _parse_width(w, h)
        width_vals.append(wv); width_known.append(wk)
    edges["width_m"] = width_vals
    edges["width_known"] = width_known

    edges["sidewalk"] = (edges["sidewalk"].map(_sidewalk)
                        if "sidewalk" in edges.columns else "unknown")
    edges["surface"] = (edges["surface"].astype(str)
                       if "surface" in edges.columns else "unknown")
    edges["maxspeed"] = edges.get("maxspeed", pd.NA)
    edges["steps"] = edges["highway"].apply(
        lambda h: (h == "steps") or (isinstance(h, list) and "steps" in h))
    edges["length_m"] = edges_m.geometry.length

    # Precompute POI geometries by category
    def _cat_points(cat):
        sub = pois_m[pois_m["category"] == cat]
        return sub

    lively = _cat_points("lively")
    help_ = _cat_points("help")
    transit = _cat_points("transit")
    cams = _cat_points("surveillance")
    risk = _cat_points("risk")

    # Buffered sjoin counts (vectorized)
    def _count_within(gdf_edges, gdf_pts, dist_m, filter_mask=None):
        if filter_mask is not None:
            gdf_pts = gdf_pts[filter_mask]
        if len(gdf_pts) == 0:
            return np.zeros(len(gdf_edges), dtype=int)
        buf = gdf_edges.copy()
        buf["geometry"] = gdf_edges.geometry.buffer(dist_m)
        joined = gpd.sjoin(buf[["segment_id", "geometry"]],
                           gdf_pts[["geometry"]], predicate="intersects",
                           how="left")
        counts = joined.groupby("segment_id").size()
        # subtract 1 for rows that had no match (sjoin left adds a NaN row)
        has_match = joined.dropna(subset=["index_right"]).groupby("segment_id").size()
        out = pd.Series(0, index=gdf_edges["segment_id"]).astype(int)
        out.update(has_match)
        return out.reindex(gdf_edges["segment_id"]).fillna(0).astype(int).values

    print("[edges] Counting lively POIs within 50 m (day & night) ...")
    lively_mask_day = lively["open_14h"].values if len(lively) else None
    lively_mask_night = lively["open_23h"].values if len(lively) else None
    edges["n_lively_open_14h"] = _count_within(edges_m, lively, 50, lively_mask_day)
    edges["n_lively_open_23h"] = _count_within(edges_m, lively, 50, lively_mask_night)

    print("[edges] Counting transit stops within 100 m ...")
    edges["n_transit_100m"] = _count_within(edges_m, transit, 100)

    print("[edges] Counting cameras within 50 m ...")
    edges["n_cameras_50m"] = _count_within(edges_m, cams, 50)

    print("[edges] Risk flags within 30 m ...")
    def _risk_mask(col, val):
        if col not in pois_m.columns: return None
        return pois_m[(pois_m["category"] == "risk") &
                     (pois_m[col].astype(str).str.lower() == val)].index
    park_pts = pois_m[(pois_m["category"] == "risk") &
                      (pois_m["leisure"].astype(str) == "park")]
    tunnel_pts = pois_m[(pois_m["category"] == "risk") &
                        (pois_m["tunnel"].notna())]
    parking_pts = pois_m[(pois_m["category"] == "risk") &
                         (pois_m["amenity"].astype(str) == "parking")]
    constr_pts = pois_m[(pois_m["category"] == "risk") &
                        (pois_m["landuse"].astype(str) == "construction")]
    edges["risk_park_30m"] = _count_within(edges_m, park_pts, 30) > 0
    edges["risk_tunnel_30m"] = _count_within(edges_m, tunnel_pts, 30) > 0
    edges["risk_parking_30m"] = _count_within(edges_m, parking_pts, 30) > 0
    edges["risk_construction_30m"] = _count_within(edges_m, constr_pts, 30) > 0

    print("[edges] Distance to nearest help POI open at 23h (cap 800 m) ...")
    def _nearest_dist(gdf_edges, gdf_pts, cap_m, mask=None):
        if mask is not None:
            gdf_pts = gdf_pts[mask]
        if len(gdf_pts) == 0:
            return np.full(len(gdf_edges), cap_m, dtype=float)
        joined = gpd.sjoin_nearest(
            gdf_edges[["segment_id", "geometry"]],
            gdf_pts[["geometry"]].reset_index(drop=True),
            how="left", max_distance=cap_m, distance_col="dist_m")
        d = joined.groupby("segment_id")["dist_m"].min()
        out = pd.Series(cap_m, index=gdf_edges["segment_id"]).astype(float)
        out.update(d)
        return out.reindex(gdf_edges["segment_id"]).fillna(cap_m).values

    help_mask_night = help_["open_23h"].values if len(help_) else None
    edges["dist_help_open_23h_m"] = _nearest_dist(edges_m, help_, 800,
                                                   help_mask_night)

    print("[edges] Distance to nearest lively POI open at 23h ...")
    edges["dist_nearest_open_venue_23h_m"] = _nearest_dist(
        edges_m, lively, 800, lively_mask_night)

    # ---- Accessibility POIs (tolerant to missing columns) ----
    access = pois_m[pois_m["category"] == "accessibility"].copy()
    empty = access.iloc[0:0]
    if len(access) and "amenity" in access.columns:
        benches = access[access["amenity"].astype(str) == "bench"]
        rest_points = access[access["amenity"].astype(str).isin(
            ["bench", "drinking_water", "toilets"])]
    else:
        benches = empty
        rest_points = empty
    kerbs = access[access["kerb"].notna()] if (
        len(access) and "kerb" in access.columns) else empty

    print("[edges] Accessibility: benches / rest points / kerbs ...")
    edges["n_benches_30m"] = _count_within(edges_m, benches, 30)
    edges["n_rest_points_50m"] = _count_within(edges_m, rest_points, 50)
    edges["n_kerbs_20m"] = _count_within(edges_m, kerbs, 20)
    # Lowered kerb nearby = good; raised = bad. We just count presence here;
    # the scorer can refine using the raw `kerb` values if needed.

    # ---- Dead-end flag: endpoint node with degree 1 ----
    print("[edges] Dead-end flag ...")
    deg = dict(G.degree())
    edges["dead_end"] = edges.apply(
        lambda r: deg.get(r["u"], 0) <= 1 or deg.get(r["v"], 0) <= 1, axis=1)

    # ---- Partner venues (loaded from JSON if present, else empty) ----
    print("[edges] Partner venues ...")
    partners_json = PROCESSED_DIR / "partner_venues.json"
    if partners_json.exists():
        import json as _json
        pdata = _json.loads(partners_json.read_text())
        if pdata:
            pdf = gpd.GeoDataFrame(
                pdata,
                geometry=gpd.points_from_xy([p["lon"] for p in pdata],
                                            [p["lat"] for p in pdata]),
                crs="EPSG:4326").to_crs(METRIC_CRS)
            edges["n_partner_venues_50m"] = _count_within(edges_m, pdf, 50)
        else:
            edges["n_partner_venues_50m"] = 0
    else:
        edges["n_partner_venues_50m"] = 0

    # ---- Simulated user reports (loaded from CSV if present) ----
    print("[edges] User reports ...")
    reports_csv = PROCESSED_DIR / "user_reports.csv"
    if reports_csv.exists():
        rdf = pd.read_csv(reports_csv)
        counts = rdf.groupby(["segment_id", "tag"]).size().unstack(fill_value=0)
        for tag in ["unsafe", "poorly_lit", "isolated", "harassment"]:
            col = f"reports_{tag}"
            edges[col] = edges["segment_id"].map(
                counts[tag] if tag in counts.columns else {}).fillna(0).astype(int)
    else:
        for tag in ["unsafe", "poorly_lit", "isolated", "harassment"]:
            edges[f"reports_{tag}"] = 0

    # Keep a clean, documented set of columns
    keep = ["segment_id", "u", "v", "key", "length_m", "name", "highway",
            "lit", "lit_known", "width_m", "width_known", "sidewalk",
            "surface", "maxspeed", "steps",
            "n_lively_open_14h", "n_lively_open_23h",
            "dist_help_open_23h_m", "n_transit_100m", "n_cameras_50m",
            "risk_park_30m", "risk_tunnel_30m", "risk_parking_30m",
            "risk_construction_30m", "dist_nearest_open_venue_23h_m",
            "n_benches_30m", "n_rest_points_50m", "n_kerbs_20m",
            "dead_end", "n_partner_venues_50m",
            "reports_unsafe", "reports_poorly_lit", "reports_isolated",
            "reports_harassment",
            "geometry"]
    for col in keep:
        if col not in edges.columns:
            edges[col] = pd.NA
    edges_out = gpd.GeoDataFrame(edges[keep], geometry="geometry", crs=edges.crs)
    edges_out = _flatten_lists(edges_out)
    return edges_out


# ---------- Main -------------------------------------------------------------

def _coverage(edges: pd.DataFrame, pois: pd.DataFrame) -> None:
    print("\n=== COVERAGE SUMMARY ===")
    print(f"edges: {len(edges)}  |  pois: {len(pois)}")
    print(f"  % edges with lit known:      {100*edges['lit_known'].mean():.1f}%")
    print(f"  % edges with width known:    {100*edges['width_known'].mean():.1f}%")
    print(f"  % edges with sidewalk known: "
          f"{100*(edges['sidewalk']!='unknown').mean():.1f}%")
    print(f"  % pois with hours known:     {100*pois['hours_known'].mean():.1f}%")
    print("  pois per category:")
    print(pois["category"].value_counts().to_string())
    print("========================\n")


def main(force: bool = False):
    t0 = time.time()
    if not GRAPH_PATH.exists():
        print("[main] graph not found, running build_graph first.")
        from scripts.build_graph import build_graph
        G = build_graph(force=force)
    else:
        G = ox.load_graphml(GRAPH_PATH)
        print(f"[main] Loaded graph: {len(G.nodes)} nodes, {len(G.edges)} edges")

    if POIS_PATH.exists() and not force:
        print(f"[main] Loading cached POIs from {POIS_PATH}")
        pois = gpd.read_parquet(POIS_PATH)
    else:
        pois = download_pois()
        pois = tag_opening_hours(pois)
        pois.to_parquet(POIS_PATH, index=False)
        print(f"[main] Saved {len(pois)} POIs -> {POIS_PATH}")

    edges = compute_edge_features(G, pois)
    edges.to_parquet(EDGES_PARQUET, index=False)
    edges.to_file(EDGES_GEOJSON, driver="GeoJSON")
    print(f"[main] Saved {len(edges)} edges -> {EDGES_PARQUET} and {EDGES_GEOJSON}")

    _coverage(edges, pois)
    print(f"[main] Done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
