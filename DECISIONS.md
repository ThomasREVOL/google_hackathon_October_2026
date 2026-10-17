# Human judgment log

Every time a human made a call that the AI couldn't — or overrode what the AI suggested — write one row.
This is the raw material for the **Judgment** and **Taste** parts of the video and README.

| Decision | What the AI suggested | What we chose | Why (the human understanding) |
|----------|-----------------------|---------------|-------------------------------|
| Which idea | Accessible transit map, then "Compagnon" (expert know-how capture) | Safe walking route + walking home together | _(team: add your reason)_ — a research check showed safety maps alone already exist (incl. at Berkeley), so we added the parts data and AI can't provide: people walking together and reporting what data misses |
| Crime data | Drop it (bias, stigmatization risk) | Keep it, filtered to pedestrian-safety categories, low reliability (0.4), never shown as "dangerous areas" | It carries real signal, but only with its bias stated; weighting each source by reliability makes that judgment explicit |
| City | Berkeley, then San Francisco for its open data | Back to Berkeley | Our data teammate checked and SF did not have enough usable data for our factors, so they gathered Berkeley data instead |
| Demo route | Valencia → Castro via Dolores Park (SF) | Downtown Berkeley BART → Unit 3 | Verified on the graph: the fastest route crosses ~400 m of Grinnell Natural Area and campus woods, the street alternative is only +35 m |
| Who computes routes | — | Our own A* on a weighted graph; Gemini only translates text ↔ numbers | Routes and scores must be explainable and must not depend on an AI that can invent facts |
| Deployment | Skip it, record on localhost | Keep it, as one Render service (FastAPI serves the page) | A live link makes the project real; one service keeps it simple |
| | | | |
