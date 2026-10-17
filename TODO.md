# To-do — Safe Route Home

> Chacun coche **uniquement sa section** (moins de conflits git). Mettre à jour après chaque tâche terminée.
> Git : `git pull --rebase` avant de commencer et avant chaque push, `git add <tes fichiers>` uniquement, jamais `git add -A` (voir README → Team git workflow).
> Repères : **T+40** point d'étape · **T+60** gel des fonctionnalités · **T+70** vidéo · **T+115** soumission

**Dernière mise à jour :** `/match` réel (matching sur les trajets sûrs, préférences respectées, SafeWalk si personne) + interface du groupe. Prochaines étapes : test dans le navigateur, enregistrements d'écran, vidéo.

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
- [x] `scripts/attach_features.py` → `data/graph.pkl` (3,5 Mo) : 100 % des segments reliés aux données de l'équipier, bois du campus ajoutés (75 polygones → `data/clean/woods.geojson`), lampadaires/pannes à `None` quand il n'y en a pas, aide = points disponibles à 23 h (53), incidents simulés filtrés, 75 signalements simulés → pénalités de départ
- [x] **Démo validée avec les données** : de nuit, le rapide passe 426 m dans les bois (score 6,8), le sûr les évite totalement pour +50 m (score 8,1) ; de jour, même trajet. Gemini l'explique (« avoids the 426 meters through parks and woods… »)
- [x] `backend/llm.py` : `profile_to_weights`, `comment_to_tags`, `explain_route`, `explain_match`, chacune avec repli + cache disque (`data/llm_cache.json`) + modèle de secours. Modèle `gemini-flash-lite-latest` (environ 1 s), car `gemini-flash-latest` était surchargé
- [x] Gemini branché dans `/route` (profil → poids + détour max, explication) et `/report` (étiquettes + gravité) : environ 1,8 s par trajet, testé
- [x] `REPORT_STEP` vérifié : 1 signalement « very dark and nobody around » (gravité 0,8) suffit à changer le trajet
- [ ] Avant d'enregistrer : jouer le scénario de démo, puis commiter `data/llm_cache.json` (`git add data/llm_cache.json`). Ne pas le commiter avant, il change à chaque test
- [x] `/match` réel (`backend/matching.py`) : fenêtres horaires, départs à moins de 400 m, préférences de groupe respectées des deux côtés, score sur le trajet sûr partagé, point de rendez-vous le plus sûr, explication Gemini, recours à SafeWalk si personne. Testé : sans préférence → Alex + Sam (Lea et Maya exclues par leur choix) ; « women-only » → Lea + Maya + Sam ; 2 h → SafeWalk
- [x] Interface du groupe : case « women-only », membres sur la carte et en liste, trajet commun, note sur les préférences, bouton d'appel SafeWalk
- [x] Fonds de carte : CARTO exige désormais une clé, remplacé par Esri Dark Gray (Night), OSM filtré en sombre (Night detailed), OSM (Light), Esri (Satellite), tous testés sans clé
- [x] Interface : fond de nuit + Clair + Satellite, bouton démo, clic départ/arrivée, trajet sûr animé et lumineux vs trajet rapide en pointillés, cartes de score, barres par facteur (couverture et fiabilité), encadré « Gemini understood », mode Signaler → nouveau trajet, panneau Rentrer ensemble, couches de données. Version téléphone en panneau du bas
- [x] `GET /layers` : points et parcs de `data/clean/` pour la carte (jamais les crimes)
- [x] En-tête `Cache-Control: no-cache` : un simple rafraîchissement affiche la dernière version déployée (avant, le navigateur gardait l'ancienne interface)
- [ ] Tester l'interface dans le navigateur (local, puis sur Render) et corriger ce qui cloche

## Données
- [x] Couche de données poussée (PR #2) : `data/clean/` (78 lampadaires, 24 lieux ouverts à 23 h, 156 points d'aide, 57 parcs), `data/clean_rich/`, `data/processed/` (graph.graphml, edges.parquet par `segment_id`), pipeline `scripts/`
- [x] Fusion réglée par l'implémentation : README réunifié, `.env` de nouveau ignoré par git, `requirements.txt` de l'app restauré (les bibliothèques de données sont passées dans `requirements-dev.txt`), notre script de graphe pour l'API renommé `scripts/build_app_graph.py`
- [x] **Décision d'équipe :** données simulées **gardées** et étiquetées « simulated » partout (badge sur le facteur, légende de la carte, Gemini, README)
- [x] Bois du campus ajoutés (`data/clean/woods.geojson`, téléchargés par `attach_features.py`) et affichés avec les parcs sur la carte
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
- [ ] **Tournage maintenant, en plein jour** (1 personne, environ 20 min) : plans A1–A7 de [demo/demo_script.md](demo/demo_script.md) (sortie de BART, chemin dans les bois, rue éclairée, Unit 3, téléphone en main, marche à plusieurs, photo d'équipe)
- [ ] Enregistrements d'écran B1–B7 (bureau + vue téléphone) une fois `graph.pkl` avec les données
- [ ] Visuels C1–C4 : vignette et carte de titre (ChatGPT), schéma « qui fait quoi », jugement, limites
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
