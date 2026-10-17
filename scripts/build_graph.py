"""Download the walking network for the demo zone and save it.

Run from repo root:
    python -m scripts.build_graph
"""
from __future__ import annotations

import sys
import time
import pandas as pd
import osmnx as ox

from scripts.config import (
    CENTER,
    RADIUS_M,
    NETWORK_TYPE,
    GRAPH_PATH,
    NODES_PARQUET,
)


def build_graph(force: bool = False):
    if GRAPH_PATH.exists() and not force:
        print(f"[build_graph] {GRAPH_PATH} already exists, loading it.")
        G = ox.load_graphml(GRAPH_PATH)
    else:
        print(f"[build_graph] Downloading walking network: center={CENTER}, "
              f"radius={RADIUS_M} m, network_type={NETWORK_TYPE}")
        t0 = time.time()
        G = ox.graph_from_point(CENTER, dist=RADIUS_M, network_type=NETWORK_TYPE)
        print(f"[build_graph] Downloaded in {time.time()-t0:.1f}s: "
              f"{len(G.nodes)} nodes, {len(G.edges)} edges")

    # Stable segment_id per edge: f"{u}_{v}_{key}"
    for u, v, k, data in G.edges(keys=True, data=True):
        data["segment_id"] = f"{u}_{v}_{k}"

    # Save graphml (preserves attributes)
    ox.save_graphml(G, GRAPH_PATH)
    print(f"[build_graph] Saved graph -> {GRAPH_PATH}")

    # Save nodes as parquet (lat, lon) for the router
    nodes_gdf, _ = ox.graph_to_gdfs(G)
    nodes_df = pd.DataFrame({
        "node_id": nodes_gdf.index,
        "lat": nodes_gdf["y"].values,
        "lon": nodes_gdf["x"].values,
    })
    nodes_df.to_parquet(NODES_PARQUET, index=False)
    print(f"[build_graph] Saved {len(nodes_df)} nodes -> {NODES_PARQUET}")

    return G


if __name__ == "__main__":
    force = "--force" in sys.argv
    build_graph(force=force)
