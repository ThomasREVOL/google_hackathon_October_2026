"""Minimal helpers for teammates to load the data layer.

The scorer and the router should both go through this module so column names
and IDs stay consistent.

    from backend.data_loader import load_graph, load_edges, load_pois, nearest_node
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import geopandas as gpd
import osmnx as ox

from scripts.config import (
    GRAPH_PATH, EDGES_PARQUET, POIS_PATH, NODES_PARQUET,
)

_GRAPH = None
_EDGES: Optional[gpd.GeoDataFrame] = None
_POIS: Optional[gpd.GeoDataFrame] = None
_NODES: Optional[pd.DataFrame] = None


def load_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = ox.load_graphml(GRAPH_PATH)
    return _GRAPH


def load_edges() -> gpd.GeoDataFrame:
    """Return a GeoDataFrame indexed by segment_id with all raw features."""
    global _EDGES
    if _EDGES is None:
        gdf = gpd.read_parquet(EDGES_PARQUET)
        _EDGES = gdf.set_index("segment_id", drop=False)
    return _EDGES


def load_pois() -> gpd.GeoDataFrame:
    global _POIS
    if _POIS is None:
        _POIS = gpd.read_parquet(POIS_PATH)
    return _POIS


def load_nodes() -> pd.DataFrame:
    global _NODES
    if _NODES is None:
        _NODES = pd.read_parquet(NODES_PARQUET)
    return _NODES


def get_edge_features(segment_id: str) -> dict:
    df = load_edges()
    if segment_id not in df.index:
        raise KeyError(segment_id)
    return df.loc[segment_id].to_dict()


def nearest_node(lat: float, lon: float):
    """Snap a (lat, lon) to the nearest graph node id."""
    G = load_graph()
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)


def apply_manual_annotations(edges: gpd.GeoDataFrame,
                             csv_path: str | Path) -> gpd.GeoDataFrame:
    """Override values from manual_annotations.csv.

    CSV columns: segment_id, field, value, note, author
    Only existing columns are overridden; the matching *_known flag (if any)
    is set to True.
    """
    path = Path(csv_path)
    if not path.exists():
        return edges
    df = pd.read_csv(path)
    for _, r in df.iterrows():
        sid, field, val = r.get("segment_id"), r.get("field"), r.get("value")
        if not isinstance(sid, str) or not isinstance(field, str):
            continue
        if sid not in edges.index or field not in edges.columns:
            continue
        try:
            edges.at[sid, field] = val
            kflag = f"{field}_known"
            if kflag in edges.columns:
                edges.at[sid, kflag] = True
        except Exception:
            continue
    return edges
