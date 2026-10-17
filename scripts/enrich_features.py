"""Optional enrichments: slope, GTFS night departures, reported incidents.

Each enrichment is wrapped in try/except and logs whether it was applied.
NO scoring: raw columns only. Run after build_features.

    python -m scripts.enrich_features
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

from scripts.config import (
    RAW_DIR, PROCESSED_DIR, METRIC_CRS, GRAPH_PATH, EDGES_PARQUET, EDGES_GEOJSON,
)

BASE_PARQUET = PROCESSED_DIR / "edges_base.parquet"


def _save(edges: gpd.GeoDataFrame):
    edges.to_parquet(EDGES_PARQUET, index=False)
    edges.to_file(EDGES_GEOJSON, driver="GeoJSON")


def enrich_slope(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add slope_pct, slope_abs_pct, steep_flag, slope_known."""
    try:
        import osmnx as ox
        G = ox.load_graphml(GRAPH_PATH)
        dem = RAW_DIR / "dem.tif"
        if dem.exists():
            try:
                import rasterio  # noqa: F401
                G = ox.elevation.add_node_elevations_raster(G, str(dem))
                src = "DEM"
            except Exception as e:
                print(f"[slope] rasterio missing or DEM unreadable: {e}; "
                      "falling back to Open-Elevation API")
                G = _add_elevations_open_elevation(G)
                src = "open-elevation"
        else:
            G = _add_elevations_open_elevation(G)
            src = "open-elevation"
        G = ox.elevation.add_edge_grades(G)
        rows = []
        for u, v, k, d in G.edges(keys=True, data=True):
            sid = f"{u}_{v}_{k}"
            g = d.get("grade")
            rows.append((sid, float(g) if g is not None else np.nan))
        grades = pd.DataFrame(rows, columns=["segment_id", "grade"])
        edges = edges.merge(grades, on="segment_id", how="left")
        edges["slope_pct"] = edges["grade"] * 100
        edges["slope_abs_pct"] = edges["slope_pct"].abs()
        edges["steep_flag"] = edges["slope_abs_pct"] > 6
        edges["slope_known"] = edges["slope_pct"].notna()
        edges = edges.drop(columns=["grade"])
        print(f"[slope] applied, source={src}, "
              f"known={100*edges['slope_known'].mean():.1f}%")
    except Exception as e:
        print(f"[slope] SKIPPED: {e}")
        traceback.print_exc(limit=1)
        for c, dv in [("slope_pct", np.nan), ("slope_abs_pct", np.nan),
                      ("steep_flag", False), ("slope_known", False)]:
            if c not in edges.columns:
                edges[c] = dv
    return edges


def _add_elevations_open_elevation(G):
    """Query https://api.open-elevation.com in batches of 100."""
    import requests
    nodes = list(G.nodes(data=True))
    coords = [(n[1]["y"], n[1]["x"]) for n in nodes]
    elevs = []
    for i in range(0, len(coords), 100):
        batch = coords[i:i+100]
        r = requests.post(
            "https://api.open-elevation.com/api/v1/lookup",
            json={"locations": [{"latitude": a, "longitude": b} for a, b in batch]},
            timeout=30)
        r.raise_for_status()
        elevs.extend(x["elevation"] for x in r.json()["results"])
    for (nid, _), e in zip(nodes, elevs):
        G.nodes[nid]["elevation"] = float(e)
    return G


def enrich_gtfs(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add n_night_departures_100m from AC Transit / BART GTFS."""
    try:
        import zipfile
        gtfs_dir = RAW_DIR / "gtfs"
        zips = list(gtfs_dir.glob("*.zip")) if gtfs_dir.exists() else []
        if not zips:
            raise FileNotFoundError(f"No GTFS zip in {gtfs_dir}")
        all_stops = []
        for z in zips:
            with zipfile.ZipFile(z) as zf:
                with zf.open("stops.txt") as f:
                    stops = pd.read_csv(f)
                with zf.open("stop_times.txt") as f:
                    st = pd.read_csv(f, dtype={"stop_id": str})
            # Count departures between 22:00 and 02:00 (handle 24:xx+)
            hh = st["departure_time"].str.slice(0, 2).astype(int, errors="ignore")
            night_mask = (hh >= 22) | (hh < 2) | (hh >= 24)
            dep = st[night_mask].groupby("stop_id").size().rename("n_night_dep")
            stops = stops.merge(dep, left_on="stop_id", right_index=True, how="left")
            stops["n_night_dep"] = stops["n_night_dep"].fillna(0).astype(int)
            all_stops.append(stops[["stop_id", "stop_lat", "stop_lon", "n_night_dep"]])
        stops_df = pd.concat(all_stops, ignore_index=True)
        gdf_stops = gpd.GeoDataFrame(
            stops_df,
            geometry=gpd.points_from_xy(stops_df["stop_lon"], stops_df["stop_lat"]),
            crs="EPSG:4326",
        ).to_crs(METRIC_CRS)
        edges_m = edges.to_crs(METRIC_CRS).copy()
        edges_m["geom_buf"] = edges_m.geometry.buffer(100)
        edges_m = edges_m.set_geometry("geom_buf")
        joined = gpd.sjoin(edges_m[["segment_id", "geom_buf"]], gdf_stops,
                           predicate="intersects", how="left")
        agg = joined.groupby("segment_id")["n_night_dep"].sum().fillna(0).astype(int)
        edges["n_night_departures_100m"] = edges["segment_id"].map(agg).fillna(0).astype(int)
        print(f"[gtfs] applied, {len(zips)} feed(s), "
              f"edges with night service: {(edges['n_night_departures_100m']>0).sum()}")
    except Exception as e:
        print(f"[gtfs] SKIPPED: {e}")
        if "n_night_departures_100m" not in edges.columns:
            edges["n_night_departures_100m"] = 0
    return edges


def enrich_incidents(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add raw reported-incident counts per 250 m grid cell and hour band.

    NOTE: This is REPORTED incidents data, biased by reporting and patrolling.
    The scoring teammate must weight it LOW and present it as "reported
    incidents", never as "danger" or "crime risk".
    """
    try:
        incidents_csv = RAW_DIR / "incidents.csv"
        if not incidents_csv.exists():
            raise FileNotFoundError(incidents_csv)
        df = pd.read_csv(incidents_csv)
        df = df.dropna(subset=["lat", "lon", "datetime"]).copy()
        df["dt"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["dt"])
        df["hour"] = df["dt"].dt.hour
        def band(h):
            if 7 <= h < 19: return "day"
            if 19 <= h < 23: return "evening"
            return "night"
        df["band"] = df["hour"].map(band)

        gdf = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df["lon"], df["lat"]),
            crs="EPSG:4326").to_crs(METRIC_CRS)
        # 250 m grid cell key
        gdf["cx"] = (gdf.geometry.x // 250).astype(int)
        gdf["cy"] = (gdf.geometry.y // 250).astype(int)
        cell_counts = (gdf.groupby(["cx", "cy", "band"]).size()
                       .unstack(fill_value=0).reset_index())
        for col in ["day", "evening", "night"]:
            if col not in cell_counts.columns:
                cell_counts[col] = 0

        edges_m = edges.to_crs(METRIC_CRS).copy()
        c = edges_m.geometry.centroid
        edges_m["cx"] = (c.x // 250).astype(int)
        edges_m["cy"] = (c.y // 250).astype(int)
        merged = edges_m[["segment_id", "cx", "cy"]].merge(
            cell_counts, on=["cx", "cy"], how="left").fillna(0)
        edges["incidents_day"] = merged["day"].astype(int).values
        edges["incidents_evening"] = merged["evening"].astype(int).values
        edges["incidents_night"] = merged["night"].astype(int).values
        edges["incident_period_covered"] = (
            f"{df['dt'].min().date()} to {df['dt'].max().date()}")
        print(f"[incidents] applied, {len(df)} incidents, "
              f"period {edges['incident_period_covered'].iloc[0]}")
    except Exception as e:
        print(f"[incidents] SKIPPED: {e}")
        for c, dv in [("incidents_day", 0), ("incidents_evening", 0),
                      ("incidents_night", 0),
                      ("incident_period_covered", "n/a")]:
            if c not in edges.columns:
                edges[c] = dv
    return edges


def main():
    t0 = time.time()
    if not EDGES_PARQUET.exists():
        raise SystemExit("Run build_features first.")
    edges = gpd.read_parquet(EDGES_PARQUET)
    # Snapshot the base before enriching, in case we need to re-run
    if not BASE_PARQUET.exists():
        edges.to_parquet(BASE_PARQUET, index=False)
        print(f"[main] Snapshot saved -> {BASE_PARQUET}")
    edges = enrich_slope(edges)
    edges = enrich_gtfs(edges)
    edges = enrich_incidents(edges)
    _save(edges)
    print(f"[main] Enriched edges saved. Done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
