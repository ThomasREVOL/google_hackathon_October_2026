"""Run locally: attach data/clean/* to graph edges, compute risk with backend.scoring, save data/graph.pkl.

- crime points -> nearest NODE (SFPD snaps incidents to intersections); edge crime = sum of its 2 end nodes, night band
- other points (lamp, light_outage, venue_late, help) -> nearest edge within 50 m
- in_park: edge midpoint inside data/clean/parks.geojson
- lit: OSM edge tag (1/0/None)
"""

# TODO
