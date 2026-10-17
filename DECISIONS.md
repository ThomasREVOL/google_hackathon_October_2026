# Human judgment log

Every time a human made a call that the AI couldn't — or overrode what the AI suggested — write one row.
This is the raw material for the **Judgment** and **Taste** parts of the video and README.

| Decision | What the AI suggested | What we chose | Why (the human understanding) |
|----------|-----------------------|---------------|-------------------------------|
| Which idea | Accessible transit map, then "Compagnon" (expert know-how capture) | Safe walking route + walking home together | _(team: add your reason)_ — a research check showed safety maps alone already exist (incl. at Berkeley), so we added the parts data and AI can't provide: people walking together and reporting what data misses |
| Crime data | Drop it (bias, stigmatization risk) | Keep it, filtered to pedestrian-safety categories, low reliability (0.4), never shown as "dangerous areas" | It carries real signal, but only with its bias stated; weighting each source by reliability makes that judgment explicit |
| City | Berkeley, then San Francisco for its open data | Back to Berkeley | Our data teammate checked and SF did not have enough usable data for our factors, so they gathered Berkeley data instead |
| What the map shows | — | Lamps, broken lights, open venues, help points, parks — but **no crime dots** | Crime data only adjusts the route score with low weight; dots on a map would label places as "dangerous" and stigmatize neighborhoods |
| Simulated data (incidents, broken lights, past reports) | Exclude it from the score | Keep it, but labelled "simulated" everywhere: score badge, map legend, Gemini explanation, README | Real Berkeley incident data was not integrated in time; the demo shows how the factor works without ever passing simulated data off as real |
| Missing data | Treat "no lamp mapped" or "no outage reported" as 0 | Treat it as unknown (None), never as dark or safe | OSM maps only 78 lamps in our zone: absence of evidence is not evidence of darkness |
| Help points | Distance to any help point | Only help available at 23:00 whatever the opening hours: emergency phones, police, fire stations, hospitals | A pharmacy closed at night does not help; opening hours were unknown for all points |
| "In a park" | Within 30 m of a park | At least half of the segment inside a park or wood | A 30 m buffer would penalize the lit streets that run along parks — exactly the alternative we want to suggest |
| Demo route | Valencia → Castro via Dolores Park (SF) | Downtown Berkeley BART → Unit 3 | Verified on the graph: the fastest route crosses ~400 m of Grinnell Natural Area and campus woods, the street alternative is only +35 m |
| Who computes routes | — | Our own A* on a weighted graph; Gemini only translates text ↔ numbers | Routes and scores must be explainable and must not depend on an AI that can invent facts |
| Deployment | Skip it, record on localhost | Keep it, as one Render service (FastAPI serves the page) | A live link makes the project real; one service keeps it simple |
| | | | |
