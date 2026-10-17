"""Run locally (requirements-dev.txt): download the walking graph of the demo zone with OSMnx.

Usage (from the repo root, venv active):  python scripts/build_app_graph.py
(scripts/build_graph.py is the data-layer pipeline; this one builds the light graph the API loads)
Output: data/graph_raw.pkl — networkx MultiDiGraph, light enough for Render (512 MB):
  nodes: x (lon), y (lat)
  edges: length (m), geometry ([[lat, lon], ...]), lit (1 / 0 / None), highway, name
"""
import pickle
from pathlib import Path

import truststore

truststore.inject_into_ssl()  # use the OS certificate store (fixes SSL errors behind proxies/antivirus)

import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "graph_raw.pkl"

CENTER = (37.8705, -122.2600)  # UC Berkeley campus (lat, lon)
DIST_M = 1500  # half-side of the bounding box: 3 x 3 km covers campus, Downtown BART, Southside, Northside

# OSM values of the "lit" tag (https://wiki.openstreetmap.org/wiki/Key:lit)
LIT_YES = {"yes", "24/7", "automatic", "limited", "interval", "sunset-sunrise", "dusk-dawn"}
LIT_NO = {"no", "disused"}


def as_list(value):
    """Simplified edges merge several OSM ways, so a tag can be a single value or a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_lit(value):
    """1 if lit, 0 if explicitly unlit, None if unknown (never guess)."""
    values = {str(v).lower() for v in as_list(value)}
    if values & LIT_NO:
        return 0
    if values & LIT_YES:
        return 1
    return None


def edge_geometry(G, u, v, data):
    """[[lat, lon], ...]; straight edges have no geometry attribute, so use their 2 end nodes."""
    if "geometry" in data:
        return [[lat, lon] for lon, lat in data["geometry"].coords]
    return [[G.nodes[u]["y"], G.nodes[u]["x"]], [G.nodes[v]["y"], G.nodes[v]["x"]]]


def main():
    # Keep the OSM tags we need on edges ("lit" is not kept by default) and put the cache out of git
    ox.settings.useful_tags_way = list(ox.settings.useful_tags_way) + ["lit"]
    ox.settings.cache_folder = str(ROOT / "data" / "raw" / "osmnx_cache")

    print(f"Downloading walking network, {DIST_M} m around {CENTER} ...")
    G_full = ox.graph_from_point(CENTER, dist=DIST_M, network_type="walk")

    # Rebuild a light graph with only the attributes the app uses
    G = nx.MultiDiGraph()
    for n, d in G_full.nodes(data=True):
        G.add_node(n, x=d["x"], y=d["y"])
    for u, v, k, d in G_full.edges(keys=True, data=True):
        G.add_edge(
            u, v, key=k,
            length=float(d["length"]),
            geometry=edge_geometry(G_full, u, v, d),
            lit=parse_lit(d.get("lit")),
            highway=as_list(d.get("highway"))[0] if d.get("highway") else None,
            name=" / ".join(map(str, as_list(d.get("name")))) or None,
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    # Stats (lit coverage goes to README -> Limits)
    edges = [d for _, _, d in G.edges(data=True)]
    known = [d["lit"] for d in edges if d["lit"] is not None]
    print(f"Nodes: {G.number_of_nodes()}  Edges: {G.number_of_edges()}")
    print(f"Total length: {sum(d['length'] for d in edges) / 1000:.1f} km")
    print(f"'lit' tag coverage: {100 * len(known) / len(edges):.1f}% of edges "
          f"({100 * sum(known) / max(len(known), 1):.1f}% of those are lit)")
    print(f"Saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
