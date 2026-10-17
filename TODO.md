# To-do — Safe Route Home

> Chacun coche **uniquement sa section** (moins de conflits git). Mettre à jour après chaque tâche terminée.
> Repères : **T+40** point d'étape · **T+60** gel des fonctionnalités · **T+70** vidéo · **T+115** soumission

**Dernière mise à jour :** squelette déployé sur Render (redéploiement automatique à chaque push sur `main`) ; clé Gemini testée en local ; prochaine étape côté implémentation : `scripts/build_graph.py`.

## Toute l'équipe
- [x] Idée, zone de démo (Mission / Castro / Dolores Park), contrats dans [SPEC.md](SPEC.md)
- [x] Squelette du repo (backend, scripts, static, data, render.yaml)
- [x] Push du squelette
- [ ] Chacun clone le repo et crée son environnement virtuel `.venv` (voir README → Run locally) — implémentation ✅
- [ ] Clé Gemini dans `.env` de chacun (voir `.env.example`), transmise en privé, jamais sur git ni dans un canal public — implémentation ✅ (testée)
- [x] `uvicorn backend.api:app --reload` → la carte s'affiche sur http://localhost:8000 (vérifié par l'implémentation)

## Implémentation (graphe, A*, API, Gemini, interface, déploiement)
- [x] Déployer le squelette sur Render (Blueprint `render_hackathon_berkeley`, service `safe-route-home`)
- [ ] Vérifier `GEMINI_API_KEY` dans Render → safe-route-home → Environment, puis mettre l'URL dans le README
- [ ] `scripts/build_graph.py` → `data/graph_raw.pkl`
- [ ] `backend/graph.py` : `load_graph`, `nearest_node`, `nearest_edge`
- [ ] `backend/routing.py` : A* rapide / sûr, `route_summary`
- [ ] `/route` branché sur le vrai graphe (risque provisoire = 0 en attendant les données)
- [ ] `scripts/attach_features.py` (dès que `data/clean/` est prêt) → `data/graph.pkl`
- [ ] `backend/llm.py` : 3 fonctions + repli + cache du scénario de démo
- [ ] `/report` → pénalité → le trajet change à l'écran
- [ ] `/match` avec `data/mock_users.json`
- [ ] Interface (à déléguer à un agent de code) : clic départ/arrivée, 2 tracés, panneau score/facteurs/explication, Signaler, Rentrer ensemble

## Données
- [ ] OSM : lampadaires, tag `lit`, lieux ouverts tard, points d'aide, parcs
- [ ] SFPD `wg3w-h783` : 12 derniers mois, catégories piétons uniquement, heure
- [ ] SF311 `vw6y-z8j6` : pannes d'éclairage, 12 derniers mois
- [ ] `data/clean/points.csv` + `data/clean/parks.geojson` au format de [SPEC.md](SPEC.md)
- [ ] Noter la couverture du tag `lit` (en %) dans la section Limites du README

## Scoring
- [ ] `edge_risk()` : normalisation de chaque facteur entre 0 et 1
- [ ] Valider `RELIABILITY` et `DEFAULT_WEIGHTS`, justifier dans [DECISIONS.md](DECISIONS.md)
- [ ] Tester sur 3 segments du scénario de démo (parc vs rue animée)

## Démo et soumission
- [ ] Vérifier sur la carte que le trajet le plus rapide traverse bien Dolores Park
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
