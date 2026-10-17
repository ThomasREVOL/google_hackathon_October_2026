// Map + calls to the API (see SPEC.md, Contract 3). All coordinates are [lat, lon].
const map = L.map("map").setView([37.8690, -122.2620], 16);  // UC Berkeley: Downtown BART -> Unit 3
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

// TODO: click to set origin/dest, POST /route, draw fast (gray) + safe (green), panel, /report, /match
