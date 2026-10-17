"""Run locally (requirements-dev.txt): attach the data layer to the light app graph -> data/graph.pkl.

Usage (from the repo root, venv active):  python scripts/attach_features.py [--refresh-woods]

Inputs
  data/graph_raw.pkl              light OSM graph (scripts/build_app_graph.py)
  data/processed/edges.parquet    per-segment features from the data teammate, joined on segment_id = "u_v_key"
  data/clean/points.csv           lamps, help points, late venues, simulated incidents / outages
  data/clean/parks.geojson        OSM parks (leisure=park)
  data/clean/woods.geojson        OSM campus woods (natural=wood...), downloaded here once
Output
  data/graph.pkl                  same graph, each edge with `features` (SPEC Contract 2) and `seed_reports`

Rules: missing information is None (unknown), never 0 (= "safe" or "dark"). Simulated sources are kept but flagged
in G.graph["meta"] so the API, the UI and Gemini always say "simulated".
"""
import json
import math
import pickle
import sys
from datetime import date
from pathlib import Path

import truststore

truststore.inject_into_ssl()  # use the OS certificate store (fixes SSL errors behind proxies/antivirus)

import numpy as np
import osmnx as ox
import pandas as pd
import shapely
from shapely import STRtree
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_GRAPH, OUT = DATA / "graph_raw.pkl", DATA / "graph.pkl"
EDGES = DATA / "processed" / "edges.parquet"
POINTS = DATA / "clean" / "points.csv"
PARKS, WOODS = DATA / "clean" / "parks.geojson", DATA / "clean" / "woods.geojson"

CENTER, DIST_M = (37.8705, -122.2600), 1500  # same box as scripts/build_app_graph.py
WOOD_TAGS = {"natural": ["wood", "scrub"], "landuse": ["forest"], "leisure": ["nature_reserve"]}

LAMP_RADIUS_M = 30
OUTAGE_RADIUS_M = 50
CRIME_SNAP_M = 60
HELP_DECAY_M = 300  # help = exp(-distance / 300)
NIGHT_HOURS = set(range(20, 24)) | set(range(0, 6))  # same as routing.is_night
PEDESTRIAN_CRIMES = {"assault", "robbery", "harassment"}  # SPEC: no property crimes
HELP_AT_NIGHT = {"phone", "police", "fire_station", "hospital"}  # available at 23:00 whatever the opening hours
SIMULATED_FACTORS = ["crime", "outage"]

# Local metric projection (good to ~1 m over 3 km)
KX = 111_320 * math.cos(math.radians(CENTER[0]))
KY = 110_540


def to_xy(lat, lon):
    return lon * KX, lat * KY


def load_woods(refresh: bool) -> dict:
    if WOODS.exists() and not refresh:
        return json.loads(WOODS.read_text(encoding="utf-8"))
    ox.settings.cache_folder = str(DATA / "raw" / "osmnx_cache")
    gdf = ox.features_from_point(CENTER, tags=WOOD_TAGS, dist=DIST_M)
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    features = []
    for _, row in gdf.iterrows():
        props = {k: row[k] for k in ("name", "natural", "landuse", "leisure") if k in row and isinstance(row[k], str)}
        features.append({"type": "Feature", "properties": {**props, "source": "OSM"}, "geometry": mapping(row.geometry)})
    fc = {"type": "FeatureCollection", "features": features}
    WOODS.write_text(json.dumps(fc), encoding="utf-8")
    print(f"Saved {len(features)} wood polygons -> {WOODS}")
    return fc


def counts_within(tree, points_xy, radius_m, n_edges) -> np.ndarray:
    """Number of points within radius of each edge."""
    counts = np.zeros(n_edges, dtype=int)
    if len(points_xy):
        _, edge_idx = tree.query([Point(p) for p in points_xy], predicate="dwithin", distance=radius_m)
        np.add.at(counts, edge_idx, 1)
    return counts


def main():
    refresh = "--refresh-woods" in sys.argv
    with open(RAW_GRAPH, "rb") as f:
        G = pickle.load(f)
    keys = list(G.edges(keys=True))
    n = len(keys)
    lines = [LineString([to_xy(lat, lon) for lat, lon in G.edges[k]["geometry"]]) for k in keys]
    tree = STRtree(lines)
    pts = pd.read_csv(POINTS)

    # Lamps and (simulated) outages near each edge. 0 nearby = unknown: OSM maps only a few lamps
    lamps = counts_within(tree, [to_xy(r.lat, r.lon) for r in pts[pts.kind == "lamp"].itertuples()], LAMP_RADIUS_M, n)
    outages = counts_within(tree, [to_xy(r.lat, r.lon) for r in pts[pts.kind == "light_outage"].itertuples()], OUTAGE_RADIUS_M, n)

    # Distance to the nearest help point available at night
    helps = pts[(pts.kind == "help") & pts.subtype.isin(HELP_AT_NIGHT)]
    help_tree = STRtree([Point(to_xy(r.lat, r.lon)) for r in helps.itertuples()])
    _, help_dist = help_tree.query_nearest(lines, return_distance=True)

    # (Simulated) pedestrian-safety incidents at night, snapped to the nearest intersection
    node_ids = np.array(list(G.nodes))
    node_xy = np.array([to_xy(d["y"], d["x"]) for _, d in G.nodes(data=True)])
    crimes = pts[(pts.kind == "crime") & pts.crime_type.isin(PEDESTRIAN_CRIMES) & pts.hour.isin(NIGHT_HOURS)]
    node_crime = {}
    for r in crimes.itertuples():
        d2 = ((node_xy - to_xy(r.lat, r.lon)) ** 2).sum(axis=1)
        i = int(np.argmin(d2))
        if d2[i] <= CRIME_SNAP_M ** 2:
            node_crime[node_ids[i].item()] = node_crime.get(node_ids[i].item(), 0) + 1
    edge_crime = np.array([node_crime.get(u, 0) + node_crime.get(v, 0) for u, v, _ in keys])
    nonzero = edge_crime[edge_crime > 0]
    p95 = float(np.percentile(nonzero, 95)) if len(nonzero) else 1.0
    crime_norm = np.minimum(1.0, np.log1p(edge_crime) / math.log1p(max(p95, 1.0)))

    # Parks + campus woods: an edge is "in park" when at least half of it is inside
    woods = load_woods(refresh)
    parks = json.loads(PARKS.read_text(encoding="utf-8"))
    green = unary_union([shape(f["geometry"]).buffer(0) for f in parks["features"] + woods["features"]])
    green_xy = shapely.transform(green, lambda coords: coords * [KX, KY])  # (lon, lat) -> local meters
    in_green = np.zeros(n, dtype=bool)
    for i in tree.query(green_xy, predicate="intersects"):
        in_green[i] = lines[i].intersection(green_xy).length >= 0.5 * lines[i].length

    # Teammate's per-segment features (venues open at 23:00, simulated community reports)
    edges = pd.read_parquet(EDGES, columns=["segment_id", "n_lively_open_23h",
                                            "reports_unsafe", "reports_poorly_lit", "reports_isolated", "reports_harassment"])
    edges = edges.set_index("segment_id")
    lively = edges["n_lively_open_23h"].to_dict()
    reports = edges[["reports_unsafe", "reports_poorly_lit", "reports_isolated", "reports_harassment"]].sum(axis=1).to_dict()

    matched = 0
    for i, (u, v, k) in enumerate(keys):
        d = G.edges[u, v, k]
        sid = f"{u}_{v}_{k}"
        matched += sid in lively
        d["features"] = {
            "lit": d.get("lit"),
            "lamps": int(lamps[i]) or None,
            "outages": int(outages[i]) or None,
            "venues_late": int(lively[sid]) if sid in lively else None,
            "help": round(math.exp(-float(help_dist[i]) / HELP_DECAY_M), 3),
            "in_park": bool(in_green[i]),
            "crime": round(float(crime_norm[i]), 3),
            "length": d["length"],
        }
        d["seed_reports"] = int(reports.get(sid, 0))

    G.graph["meta"] = {
        "built": date.today().isoformat(),
        "simulated_factors": SIMULATED_FACTORS,
        "simulated_reports": True,
        "sources": {
            "lit": "OSM lit tag", "lamps": "OSM street lamps", "outages": "SIMULATED", "venues_late": "OSM opening_hours",
            "help": "OSM emergency phones, police, fire stations, hospitals", "in_park": "OSM parks + natural=wood",
            "crime": "SIMULATED (assault, robbery, harassment at night)", "reports": "SIMULATED community reports",
        },
    }
    with open(OUT, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    total_len = sum(G.edges[k]["length"] for k in keys)
    park_len = sum(G.edges[k]["length"] for i, k in enumerate(keys) if in_green[i])
    print(f"Edges: {n}, joined with teammate's segments: {matched} ({100 * matched / n:.1f}%)")
    print(f"In parks/woods: {int(in_green.sum())} edges ({100 * park_len / total_len:.1f}% of length) | wood polygons: {len(woods['features'])}")
    print(f"Edges with lamps nearby: {(lamps > 0).sum()} | with simulated outages: {(outages > 0).sum()} | "
          f"with venues open at 23:00: {sum(1 for k in keys if (G.edges[k]['features']['venues_late'] or 0) > 0)}")
    print(f"Help points used: {len(helps)} | median distance to help: {np.median(help_dist):.0f} m")
    print(f"Simulated night incidents kept: {len(crimes)} -> edges with crime > 0: {(edge_crime > 0).sum()} | "
          f"edges with simulated reports: {sum(1 for k in keys if G.edges[k]['seed_reports'])}")
    print(f"Saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
