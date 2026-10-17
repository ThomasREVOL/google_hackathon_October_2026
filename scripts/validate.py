"""Validate the data layer and produce a debug map + a data dictionary.

    python -m scripts.validate
"""
from __future__ import annotations

import json
from pathlib import Path

import folium
import pandas as pd
import geopandas as gpd

from scripts.config import PROCESSED_DIR, CENTER, EDGES_PARQUET, POIS_PATH
from backend.data_loader import load_edges, load_pois, load_graph

DEBUG_MAP = PROCESSED_DIR / "debug_map.html"
README_DATA = PROCESSED_DIR / "README_data.md"
SAMPLE_JSON = PROCESSED_DIR / "sample_edges.json"
MANUAL_CSV = PROCESSED_DIR / "manual_annotations.csv"


def checks(edges: gpd.GeoDataFrame, pois: gpd.GeoDataFrame):
    print("\n=== CHECKS ===")
    assert edges["segment_id"].is_unique, "segment_id not unique"
    assert (edges["length_m"] >= 0).all(), "negative length"
    G = load_graph()
    try:
        import networkx as nx
        G_u = G.to_undirected()
        comps = list(nx.connected_components(G_u))
        largest = max(comps, key=len)
        print(f"  largest connected component share: "
              f"{100*len(largest)/len(G_u.nodes):.1f}%")
    except Exception as e:
        print(f"  connectivity check skipped: {e}")
    print(f"  edges: {len(edges)}, pois: {len(pois)}")
    for c in ["lit_known", "width_known"]:
        if c in edges.columns:
            print(f"  % {c}: {100*edges[c].mean():.1f}%")
    print("  POIs per category:")
    print(pois["category"].value_counts().to_string())


def build_debug_map(edges: gpd.GeoDataFrame, pois: gpd.GeoDataFrame):
    m = folium.Map(location=list(CENTER), zoom_start=15, tiles="cartodbpositron")
    # Color by lit
    def color(row):
        if row.get("lit_known") and row.get("lit") == 1: return "#2ecc71"
        if row.get("lit_known") and row.get("lit") == 0: return "#e74c3c"
        return "#95a5a6"
    for _, r in edges.iterrows():
        geom = r.geometry
        if geom is None or geom.is_empty: continue
        try:
            coords = [(y, x) for x, y in geom.coords]
        except Exception:
            continue
        folium.PolyLine(
            coords, color=color(r), weight=2,
            tooltip=(f"{r.get('name','')} | {r.get('segment_id')}<br>"
                     f"len={r.get('length_m',0):.0f}m | "
                     f"lit={r.get('lit')} known={r.get('lit_known')}<br>"
                     f"n_lively_23h={r.get('n_lively_open_23h',0)} "
                     f"help_dist={r.get('dist_help_open_23h_m',0):.0f}m"),
        ).add_to(m)
    cat_colors = {"lively":"orange","help":"blue","transit":"purple",
                  "surveillance":"black","risk":"red"}
    for cat, col in cat_colors.items():
        fg = folium.FeatureGroup(name=f"POI: {cat}", show=(cat=="help"))
        sub = pois[pois["category"] == cat]
        for _, r in sub.iterrows():
            folium.CircleMarker(
                [r["lat"], r["lon"]], radius=3, color=col, fill=True,
                tooltip=f"{cat}: {r.get('name','?')} ({r.get('amenity') or r.get('shop') or ''})"
            ).add_to(fg)
        fg.add_to(m)
    folium.LayerControl().add_to(m)
    m.save(DEBUG_MAP)
    print(f"  debug map -> {DEBUG_MAP}")


def extreme_edges(edges: gpd.GeoDataFrame):
    print("\n=== 15 longest edges with NO lit info AND no open venue at 23h ===")
    sub = edges[(~edges["lit_known"]) & (edges["n_lively_open_23h"] == 0)]
    sub = sub.sort_values("length_m", ascending=False).head(15)
    for _, r in sub.iterrows():
        print(f"  {r['segment_id']:>20} | {r.get('name','?'):30} | "
              f"{r['length_m']:.0f}m")


def coverage_table(edges, pois):
    rows = []
    for c in ["lit_known", "width_known"]:
        if c in edges.columns:
            rows.append((c, f"{100*edges[c].mean():.1f}%"))
    rows.append(("sidewalk != unknown",
                 f"{100*(edges['sidewalk']!='unknown').mean():.1f}%"))
    rows.append(("pois hours_known", f"{100*pois['hours_known'].mean():.1f}%"))
    return rows


def write_readme(edges, pois):
    rows = coverage_table(edges, pois)
    cols = [
        ("segment_id", "str", "unique id = f'{u}_{v}_{key}' from the graph"),
        ("u, v, key", "int,int,int", "OSMnx graph edge endpoints + key"),
        ("length_m", "float", "edge length in metres (projected)"),
        ("name", "str", "street name (OSM, may be missing)"),
        ("highway", "str/list", "OSM highway tag"),
        ("lit", "float", "1=yes, 0=no, NaN=unknown"),
        ("lit_known", "bool", "True if OSM 'lit' tag was present"),
        ("width_m", "float", "width in metres, estimated from highway if unknown"),
        ("width_known", "bool", "True if OSM 'width' tag was present"),
        ("sidewalk", "str", "yes / no / unknown"),
        ("surface", "str", "OSM surface tag"),
        ("maxspeed", "any", "OSM maxspeed tag"),
        ("steps", "bool", "True if highway=steps"),
        ("n_lively_open_14h", "int", "lively POIs open at 14h within 50 m"),
        ("n_lively_open_23h", "int", "lively POIs open at 23h within 50 m"),
        ("dist_help_open_23h_m", "float", "metres to nearest help POI open at 23h (cap 800)"),
        ("n_transit_100m", "int", "transit stops within 100 m"),
        ("n_cameras_50m", "int", "surveillance cameras within 50 m"),
        ("risk_park_30m", "bool", "a park within 30 m"),
        ("risk_tunnel_30m", "bool", "a tunnel within 30 m"),
        ("risk_parking_30m", "bool", "a parking lot within 30 m"),
        ("risk_construction_30m", "bool", "construction within 30 m"),
        ("dist_nearest_open_venue_23h_m", "float", "metres to nearest lively POI open at 23h (cap 800)"),
        ("slope_pct, slope_abs_pct, steep_flag, slope_known",
         "optional", "from enrich_features (elevation)"),
        ("n_night_departures_100m", "optional int",
         "from enrich_features (GTFS 22-02h departures)"),
        ("incidents_day, incidents_evening, incidents_night, incident_period_covered",
         "optional", "from enrich_features; REPORTED incidents, biased"),
        ("geometry", "LineString", "WGS84 (EPSG:4326)"),
    ]
    with open(README_DATA, "w") as f:
        f.write("# Data layer\n\n")
        f.write("No scores are computed here. Scorer and router both load via\n"
                "`from backend.data_loader import load_graph, load_edges`.\n\n")
        f.write("## Coverage\n\n")
        for n, v in rows:
            f.write(f"- **{n}**: {v}\n")
        f.write("\n## Columns of edges.parquet\n\n| name | type | meaning |\n|---|---|---|\n")
        for n, t, m in cols:
            f.write(f"| `{n}` | {t} | {m} |\n")
        f.write(
            "\n## Known limitations\n"
            "- OSM coverage is uneven; many `lit` tags and `opening_hours` are missing.\n"
            "- Opening hours fall back to a per-amenity heuristic when the tag is absent.\n"
            "- `incidents_*` is REPORTED incidents, biased by reporting and patrolling.\n"
            "- Width is estimated from highway type when unknown.\n"
            "\n## Manual annotations\n"
            "Edit `manual_annotations.csv` (columns: segment_id, field, value, note, author).\n"
            "Call `apply_manual_annotations(edges, path)` from `data_loader` to override.\n"
        )
    print(f"  data dictionary -> {README_DATA}")


def write_sample(edges):
    sample = edges.head(20).copy()
    sample["geometry_wkt"] = sample.geometry.apply(lambda g: g.wkt if g else None)
    sample = sample.drop(columns=["geometry"])
    SAMPLE_JSON.write_text(sample.to_json(orient="records", indent=2))
    print(f"  sample edges -> {SAMPLE_JSON}")


def write_manual_template():
    if MANUAL_CSV.exists(): return
    pd.DataFrame(
        [{"segment_id": "", "field": "lit", "value": "", "note": "", "author": ""}]
    ).to_csv(MANUAL_CSV, index=False)
    print(f"  manual annotations template -> {MANUAL_CSV}")


def main():
    edges = load_edges()
    pois = load_pois()
    checks(edges, pois)
    build_debug_map(edges, pois)
    extreme_edges(edges)
    write_readme(edges, pois)
    write_sample(edges)
    write_manual_template()
    print("\nAll good. Push data/processed/* to the data branch.")


if __name__ == "__main__":
    main()
