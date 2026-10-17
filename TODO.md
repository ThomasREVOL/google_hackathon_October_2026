# To-do — Safe Route Home

> Chacun coche **uniquement sa section** (moins de conflits git). Mettre à jour après chaque tâche terminée.
> Git : `git pull --rebase` avant de commencer et avant chaque push, `git add <tes fichiers>` uniquement, jamais `git add -A` (voir README → Team git workflow).
> Repères : **T+40** point d'étape · **T+60** gel des fonctionnalités · **T+70** vidéo · **T+115** soumission

**Dernière mise à jour :** passage à **Berkeley** (graphe reconstruit, scénario BART → Unit 3 validé) ; `graph.py` et `routing.py` (A*) écrits et testés ; `/route` et `/report` branchés sur le vrai graphe. Prochaine étape côté implémentation : `scripts/attach_features.py` dès que `data/clean/` arrive, et en parallèle `backend/llm.py` + l'interface.

## Toute l'équipe
- [x] Idée, zone de démo (**Berkeley** : campus, Downtown, Southside, Northside), contrats dans [SPEC.md](SPEC.md)
- [x] Squelette du repo (backend, scripts, static, data, render.yaml)
- [x] Push du squelette
- [ ] Chacun clone le repo et crée son environnement virtuel `.venv` (voir README → Run locally) — implémentation ✅
- [ ] Clé Gemini dans `.env` de chacun (voir `.env.example`), transmise en privé, jamais sur git ni dans un canal public — implémentation ✅ (testée)
- [x] `uvicorn backend.api:app --reload` → la carte s'affiche sur http://localhost:8000 (vérifié par l'implémentation)

## Implémentation (graphe, A*, API, Gemini, interface, déploiement)
- [x] Déployer le squelette sur Render (Blueprint `render_hackathon_berkeley`, service `safe-route-home`)
- [x] URL dans le README : https://safe-route-home.onrender.com
- [ ] Vérifier `GEMINI_API_KEY` dans Render → safe-route-home → barre de gauche, section **MANAGE** → **Environment**
- [x] `scripts/build_graph.py` → `data/graph_raw.pkl` pour **Berkeley** (5 396 nœuds, 14 452 segments, 2,5 Mo)
- [x] `backend/graph.py` : `load_graph` (prend `graph.pkl` s'il existe, sinon `graph_raw.pkl`), `nearest_node`, `nearest_edge`
- [x] `backend/routing.py` : A* rapide / sûr, détour max 1,4×, `route_summary` (score, confiance, facteurs, couverture), `plan()` — environ 0,2 s puis 0,03 s grâce au cache
- [x] `/route` branché sur le vrai graphe (explication = modèle de texte en attendant Gemini)
- [x] `/report` → pénalité sur le segment le plus proche (dans les 2 sens), testé : le trajet sûr change
- [ ] `scripts/attach_features.py` (dès que `data/clean/` est prêt) → `data/graph.pkl`, avec `help` et `crime` normalisés et `None` pour les sources absentes (voir SPEC → Contract 2)
- [ ] `backend/llm.py` : 3 fonctions + repli + cache du scénario de démo, puis les brancher dans `/route` et `/report`
- [ ] `/match` avec `data/mock_users.json` (utilisateurs déplacés à Downtown BART → Unit 3 / Southside)
- [ ] Interface (à déléguer à un agent de code) : clic départ/arrivée, 2 tracés, panneau score/facteurs/explication, Signaler, Rentrer ensemble. Format de réponse : SPEC → Contract 3

## Données
- [ ] Sources Berkeley trouvées : **noter le nom exact et le lien de chaque jeu de données** dans README → Data sources
- [ ] OSM : lampadaires, lieux ouverts tard, points d'aide
- [ ] Parcs et bois en polygones : `leisure=park|garden|nature_reserve`, **`natural=wood|scrub`**, `landuse=forest` (le Grinnell Natural Area et les bois du campus sont en `natural=wood`, et ce sont eux qui font la différence dans la démo)
- [ ] Incidents signalés : 12 derniers mois, catégories piétons uniquement, heure
- [ ] `data/clean/points.csv` + `data/clean/parks.geojson` au format de [SPEC.md](SPEC.md). **Si une source n'existe pas, ne pas mettre de lignes de ce type** (sinon 0 lampadaire = « sombre partout »)
- [x] Couverture du tag `lit` à Berkeley : **7,5 % des segments** (88 % « lit »), notée dans README → Limits. Une valeur manquante = inconnu, pas sombre

## Scoring
- [x] `edge_risk()` : normalisation de chaque facteur entre 0 et 1, inconnu ≠ risque, métadonnées de confiance (vérifié avec `routing.py` par l'implémentation)
- [ ] Valider `RELIABILITY` et `DEFAULT_WEIGHTS`, justifier dans [DECISIONS.md](DECISIONS.md)
- [ ] Tester sur 3 segments du scénario de démo (bois du campus vs rue) une fois `graph.pkl` construit

## Démo et soumission
- [x] Scénario vérifié sur le graphe : **Downtown Berkeley BART → Unit 3**. Le plus rapide (1 495 m) traverse environ 420 m du Grinnell Natural Area et d'un bois du campus ; le contournement par les rues fait +35 m (+2 %). Secours : Channing & Telegraph → BART
- [ ] **T+40 point d'étape :** rapide vs sûr avec les vraies données, en ligne ? Sinon, la mise en relation reste codée en dur
- [ ] **T+60 gel des fonctionnalités**
- [ ] Réveiller le service Render, tester le scénario de démo 2 fois
- [ ] README final et [DECISIONS.md](DECISIONS.md) à jour
- [ ] Vidéo (T+70 → T+110), selon [demo/demo_script.md](demo/demo_script.md)
- [ ] Lien YouTube dans le README, push, soumission

## Si on est en retard, couper dans cet ordre
1. Curseurs d'après trajet
2. Mise en relation calculée → groupe codé en dur
3. Profil en texte libre → 3 préréglages

**À ne jamais couper :** rapide vs sûr avec explication, et un signalement qui change le trajet.
