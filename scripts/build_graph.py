"""Run locally (requirements-dev.txt): download the walking graph of the demo zone with OSMnx.

Output: data/graph_raw.pkl (networkx MultiDiGraph, nodes with x/y, edges with length/geometry).
"""
import truststore

truststore.inject_into_ssl()  # use the OS certificate store (fixes SSL errors behind proxies/antivirus)

CENTER = (37.7600, -122.4269)  # Dolores Park, San Francisco
DIST_M = 2000

# TODO: ox.graph_from_point(CENTER, dist=DIST_M, network_type="walk") -> pickle to data/graph_raw.pkl
