// Shared Leaflet map instance and marker registry.
// DynamicMap hook (the map <div>) writes _map once on mount.
// DMarkItem hooks (the invisible stream sentinels) read it.
let _map = null;
const _markers = new Map(); // dom_id -> L.Marker

// ---------------------------------------------------------------------------
// DynamicMap — initialises the Leaflet map
// ---------------------------------------------------------------------------

window.Hooks = window.Hooks ?? {};

window.Hooks.DynamicMap = {
  mounted() {
    _map = L.map(this.el).setView([39.5, -98.35], 4);
    L.tileLayer("http://{s}.tile.osm.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(_map);
  },
};

// ---------------------------------------------------------------------------
// DMarkItem — one hook per stream sentinel <div>
//   mounted()   → add a Leaflet marker
//   updated()   → move the Leaflet marker to new lat/lng
//   destroyed() → remove the Leaflet marker
// ---------------------------------------------------------------------------

window.Hooks.DMarkItem = {
  mounted() {
    if (!_map) return;
    const { name, lat, lng } = this.el.dataset;

    const icon = L.divIcon({
      className: "",
      html: `<div style="
        background:#2563eb;border:2px solid #fff;border-radius:50%;
        width:12px;height:12px;box-shadow:0 1px 3px rgba(0,0,0,.4)">
      </div>`,
      iconSize: [12, 12],
      iconAnchor: [6, 6],
    });

    const marker = L.marker([parseFloat(lat), parseFloat(lng)], {
      icon,
      dmarkName: name,
    })
      .addTo(_map)
      .bindTooltip(name, { permanent: false, direction: "top" });

    _markers.set(this.el.id, marker);
    _log("add", `＋ ${name} appeared`);
  },

  updated() {
    const marker = _markers.get(this.el.id);
    if (!marker) return;
    const { lat, lng } = this.el.dataset;
    marker.setLatLng([parseFloat(lat), parseFloat(lng)]);
    _log("update", `→ ${marker.options.dmarkName} moved`);
  },

  destroyed() {
    const marker = _markers.get(this.el.id);
    if (!marker) return;
    const name = marker.options.dmarkName;
    marker.remove();
    _markers.delete(this.el.id);
    _log("delete", `✕ ${name} removed`);
  },
};

// ---------------------------------------------------------------------------
// Activity log helper
// ---------------------------------------------------------------------------

function _log(type, message) {
  const log = document.getElementById("dmap-log");
  if (!log) return;

  const entry = document.createElement("div");
  entry.className = `log-${type}`;
  const ts = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  entry.textContent = `${ts}  ${message}`;
  log.prepend(entry);

  while (log.children.length > 60) {
    log.removeChild(log.lastChild);
  }
}
