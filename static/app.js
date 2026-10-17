// Map + calls to the API (see SPEC.md, Contract 3). All coordinates are [lat, lon].

// ---------- Base maps (free, no key; CARTO now requires a key) ----------
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const osm = function (className) {
  return L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: OSM_ATTR, className: className || "" });
};
const baseLayers = {
  // Esri Dark Gray Canvas: clean, presentation look; sharp up to zoom 16 (upscaled beyond)
  "Night": L.layerGroup([
    L.tileLayer(ESRI + "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, maxNativeZoom: 16, attribution: "Tiles &copy; Esri" }),
    L.tileLayer(ESRI + "Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, maxNativeZoom: 16 }),
  ]),
  // OpenStreetMap with a dark CSS filter: every footpath visible, sharp at all zooms
  "Night (detailed)": osm("tiles-night"),
  "Light": osm(),
  "Satellite": L.layerGroup([
    L.tileLayer(ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, attribution: "Imagery &copy; Esri" }),
    L.tileLayer(ESRI + "Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19 }),
  ]),
};

const map = L.map("map", { zoomControl: false, layers: [baseLayers["Night"]] }).setView([37.8690, -122.2620], 16);  // UC Berkeley
L.control.zoom({ position: "topright" }).addTo(map);
const layerControl = L.control.layers(baseLayers, {}, { position: "topright", collapsed: true }).addTo(map);
const pointsRenderer = L.canvas({ padding: 0.5 });

// ---------- State ----------
const DEMO = {
  origin: [37.8701, -122.2681],  // Downtown Berkeley BART
  dest: [37.8669, -122.2560],    // Unit 3 residence halls
  profile: "I walk alone, I prefer busy streets even if it's longer",
  time: "23:00",
};
const FACTOR_LABELS = {
  light: "Lighting", outage: "Broken streetlights", lively: "Lively streets",
  help: "Help nearby", park: "Parks & woods", crime: "Reported incidents",
};
let origin = null, dest = null, originMarker = null, destMarker = null;
let reportMode = false, pendingReport = null, lastResult = null;
const routeLayer = L.layerGroup().addTo(map);
const extraLayer = L.layerGroup().addTo(map);  // reports + walk-together

const $ = (id) => document.getElementById(id);

// ---------- Helpers ----------
function pin(cls, text) {
  return L.divIcon({ className: "", html: '<div class="pin ' + cls + '">' + text + "</div>", iconSize: [30, 30], iconAnchor: [15, 15] });
}

function toast(message, ms) {
  const t = $("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(function () { t.hidden = true; }, ms || 3500);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(path + " → HTTP " + res.status);
  return res.json();
}

// Draw a polyline progressively (SVG stroke animation)
function animate(layer, ms) {
  const path = layer.getElement && layer.getElement();
  if (!path || !path.getTotalLength) return;
  const len = path.getTotalLength();
  path.style.transition = "none";
  path.style.strokeDasharray = len + " " + len;
  path.style.strokeDashoffset = String(len);
  path.getBoundingClientRect();
  path.style.transition = "stroke-dashoffset " + (ms || 1400) + "ms ease-out";
  path.style.strokeDashoffset = "0";
  setTimeout(function () { path.style.strokeDasharray = ""; path.style.transition = ""; }, (ms || 1400) + 50);
}

function fitTo(latlngs) {
  const wide = window.innerWidth > 760;
  map.fitBounds(L.latLngBounds(latlngs), {
    paddingTopLeft: wide ? [430, 90] : [30, 90],
    paddingBottomRight: wide ? [70, 40] : [30, Math.round(window.innerHeight * 0.58) + 20],
    maxZoom: 16,  // the Night basemap is sharpest at 16
  });
}

function setHint(text) { $("hint").textContent = text; }

function setPoints(o, d) {
  origin = o; dest = d;
  if (originMarker) map.removeLayer(originMarker);
  if (destMarker) map.removeLayer(destMarker);
  originMarker = origin ? L.marker(origin, { icon: pin("a", "A") }).addTo(map) : null;
  destMarker = dest ? L.marker(dest, { icon: pin("b", "B") }).addTo(map) : null;
  $("go").disabled = !(origin && dest);
  setHint(!origin ? "Tap the map to set your start." : !dest ? "Now tap your destination." : "Ready. Tell us how you like to walk, then find your route.");
}

// ---------- Route ----------
async function findRoute(rerouted) {
  if (!origin || !dest) return;
  const go = $("go");
  go.classList.add("busy"); go.disabled = true;
  try {
    const r = await api("/route", { origin: origin, dest: dest, profile_text: $("profile").value, time: $("time").value || "23:00" });
    lastResult = r;
    drawRoutes(r);
    renderResults(r, rerouted);
  } catch (e) {
    toast("Could not compute the route: " + e.message, 5000);
  } finally {
    go.classList.remove("busy"); go.disabled = false;
  }
}

function drawRoutes(r) {
  routeLayer.clearLayers();
  L.polyline(r.fast_path, { color: "#9aa4b5", weight: 4, opacity: 0.85, dashArray: "2 9", lineCap: "round" })
    .bindTooltip("Fastest", { sticky: true }).addTo(routeLayer);
  L.polyline(r.safe_path, { color: "#34d399", weight: 14, opacity: 0.18, lineCap: "round" }).addTo(routeLayer);
  const safe = L.polyline(r.safe_path, { color: "#34d399", weight: 5, opacity: 1, lineCap: "round", className: "route-safe" })
    .bindTooltip("Safer", { sticky: true }).addTo(routeLayer);
  animate(safe, 1600);
  fitTo(r.fast_path.concat(r.safe_path));
}

function renderResults(r, rerouted) {
  $("results").hidden = false;
  $("rerouted").hidden = !rerouted;

  const p = r.profile || {};
  const understood = $("understood");
  if (p.summary) {
    understood.innerHTML = "<b>✦ Gemini understood:</b> ";
    understood.appendChild(document.createTextNode(p.summary + " Edit your text above to correct it."));
    understood.hidden = false;
  } else {
    understood.hidden = true;
  }

  [["fast", r.fast], ["safe", r.safe]].forEach(function (pair) {
    const s = pair[1];
    $(pair[0] + "-score").innerHTML = s.score + "<small>/10</small>";
    $(pair[0] + "-meta").textContent = s.length_m + " m · " + s.duration_min + " min · confidence " + Math.round(s.confidence * 100) + "%";
  });

  $("explanation").textContent = r.explanation;
  $("explanation-source").textContent = (r.explanation_source === "fallback")
    ? "Template explanation (Gemini unavailable)"
    : "✦ Explained by Gemini, using only the facts our algorithm computed";

  const warnings = [];
  if (r.coverage_warning) warnings.push(r.coverage_warning);
  if (p.unsupported_needs && p.unsupported_needs.length) warnings.push("No data yet for: " + p.unsupported_needs.join(", "));
  $("warning").textContent = warnings.join(" · ");
  $("warning").hidden = warnings.length === 0;

  const box = $("factors");
  box.innerHTML = "";
  r.safe.factors.forEach(function (f, i) {
    const fast = r.fast.factors[i];
    const row = document.createElement("div");
    row.className = "factor";
    const top = '<div class="top"><span>' + (FACTOR_LABELS[f.name] || f.name) + "</span><span>data on " +
      Math.round(f.coverage * 100) + "% of route · reliability " + f.reliability + "</span></div>";
    if (f.risk === null && (!fast || fast.risk === null)) {
      row.innerHTML = top + '<div class="nodata">No data on these routes — not counted as risk</div>';
    } else {
      const pct = function (x) { return x === null || x === undefined ? 0 : Math.round((1 - x) * 100); };
      row.innerHTML = top + '<div class="bar fast"><i style="width:0"></i></div><div class="bar safe"><i style="width:0"></i></div>';
      const bars = row.querySelectorAll(".bar i");
      setTimeout(function () { bars[0].style.width = pct(fast && fast.risk) + "%"; bars[1].style.width = pct(f.risk) + "%"; }, 50);
    }
    box.appendChild(row);
  });
}

// ---------- Report a spot (human in the loop) ----------
function toggleReport(on) {
  reportMode = on;
  $("report-btn").classList.toggle("active", on);
  $("report-btn").textContent = on ? "Tap the street to report…" : "⚑ Report a spot";
  map.getContainer().style.cursor = on ? "crosshair" : "";
}

async function sendReport() {
  const comment = $("report-text").value.trim() || "Felt unsafe here";
  $("report-modal").hidden = true;
  const at = pendingReport;
  try {
    const rep = await api("/report", { lat: at.lat, lon: at.lng, comment: comment });
    L.polyline(rep.segment.geometry, { color: "#f87171", weight: 8, opacity: 0.95, lineCap: "round", className: "report-seg" })
      .bindTooltip("Reported: " + rep.tags.join(", ")).addTo(extraLayer);
    toast("Tagged by Gemini: " + rep.tags.join(", ") + " · severity " + rep.severity + " → rerouting…", 4000);
    await findRoute(true);
  } catch (e) {
    toast("Report failed: " + e.message, 5000);
  }
}

// ---------- Walk together ----------
async function walkTogether() {
  if (!origin || !dest) return toast("Set a start and a destination first.");
  const btn = $("match-btn");
  btn.classList.add("busy");
  try {
    const t = $("time").value || "23:00";
    const m = await api("/match", { user_id: "me", origin: origin, dest: dest, window: [t, t], profile: {} });
    const mp = [m.meeting_point.lat, m.meeting_point.lon];
    const shared = L.polyline(m.shared_route, { color: "#a78bfa", weight: 5, opacity: 0.95, dashArray: "1 10", lineCap: "round", className: "route-match" }).addTo(extraLayer);
    animate(shared, 1200);
    L.marker(mp, { icon: pin("meet", "★") }).bindPopup("Meeting point: " + m.meeting_point.label).addTo(extraLayer).openPopup();
    const box = $("match");
    box.innerHTML = "<b>Walking home together</b>";
    const avatars = document.createElement("div");
    avatars.className = "avatars";
    m.group.forEach(function (u) {
      const a = document.createElement("div");
      a.className = "avatar"; a.title = u.name; a.textContent = (u.name || "?").slice(0, 1);
      avatars.appendChild(a);
    });
    box.appendChild(avatars);
    const p = document.createElement("p");
    p.textContent = m.explanation;
    box.appendChild(p);
    const ul = document.createElement("ul");
    m.safeguards.forEach(function (s) { const li = document.createElement("li"); li.textContent = s; ul.appendChild(li); });
    box.appendChild(ul);
    box.hidden = false;
  } catch (e) {
    toast("Matching failed: " + e.message, 5000);
  } finally {
    btn.classList.remove("busy");
  }
}

// ---------- Data layers (from data/clean via /layers) ----------
async function loadLayers() {
  try {
    const d = await api("/layers");
    if (d.parks) {
      layerControl.addOverlay(L.geoJSON(d.parks, { style: { color: "#22c55e", weight: 1, fillOpacity: 0.18 } }).addTo(map), "Parks & woods");
    }
    const styles = {
      lamp: ["Street lamps", "#fbbf24", 2, false],
      light_outage: ["Broken streetlights (simulated demo data)", "#f97316", 4, true],
      venue_late: ["Open late", "#e879f9", 3, false],
      help: ["Help points", "#60a5fa", 5, true],
    };
    Object.keys(styles).forEach(function (kind) {
      const pts = d.points[kind] || [];
      if (!pts.length) return;
      const s = styles[kind];
      const group = L.layerGroup(pts.map(function (p) {
        return L.circleMarker(p, { renderer: pointsRenderer, radius: s[2], color: s[1], weight: 0, fillOpacity: 0.85 });
      }));
      if (s[3]) group.addTo(map);
      layerControl.addOverlay(group, s[0] + " (" + pts.length + ")");
    });
  } catch (e) {
    console.warn("No data layers yet", e);
  }
}

// ---------- Events ----------
map.on("click", function (e) {
  if (reportMode) {
    pendingReport = e.latlng;
    toggleReport(false);
    $("report-text").value = "";
    $("report-modal").hidden = false;
    $("report-text").focus();
    return;
  }
  const p = [e.latlng.lat, e.latlng.lng];
  if (!origin || (origin && dest)) { setPoints(p, null); routeLayer.clearLayers(); }
  else setPoints(origin, p);
});

$("go").addEventListener("click", function () { findRoute(false); });
$("demo-btn").addEventListener("click", function () {
  extraLayer.clearLayers();
  $("match").hidden = true;
  $("profile").value = DEMO.profile;
  $("time").value = DEMO.time;
  setPoints(DEMO.origin, DEMO.dest);
  findRoute(false);
});
$("report-btn").addEventListener("click", function () {
  if (!lastResult) return toast("Find a route first.");
  toggleReport(!reportMode);
});
$("report-cancel").addEventListener("click", function () { $("report-modal").hidden = true; });
$("report-send").addEventListener("click", sendReport);
$("match-btn").addEventListener("click", walkTogether);

loadLayers();
