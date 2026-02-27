// Shared Leaflet map instance and marker registry.
// DynamicMap hook (the map <div>) writes _map once on mount.
// DMarkItem hooks (the invisible stream sentinels) read it.
let _map = null;
const _markers = new Map(); // dom_id -> L.Marker

// ---------------------------------------------------------------------------
// DynamicMap — initialises the Leaflet map and wires all map-level events
// ---------------------------------------------------------------------------

window.Hooks = window.Hooks ?? {};

// Map events pushed to the server (with their payload builders).
// High-frequency continuous events (move, zoom, movestart, zoomstart) are
// omitted — they fire on every animation frame during pan/zoom.
const MAP_EVENTS = [
  "click", "dblclick", "contextmenu",
  "mouseover", "mouseout",
  "moveend", "zoomend", "zoomlevelschange", "resize",
  "locationfound", "locationerror",
  "popupopen", "popupclose",
  "tooltipopen", "tooltipclose",
  "layeradd", "layerremove",
];

window.Hooks.DynamicMap = {
  mounted() {
    _map = L.map(this.el).setView([39.5, -98.35], 4);
    L.tileLayer("http://{s}.tile.osm.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(_map);

    // Wire all low-frequency map events
    MAP_EVENTS.forEach((evtName) => {
      _map.on(evtName, (e) => {
        const center = _map.getCenter();
        this.pushEvent("map-event", {
          event: evtName,
          latLng: e.latlng ? [e.latlng.lat, e.latlng.lng] : null,
          center: [center.lat, center.lng],
          zoom: _map.getZoom(),
        });
      });
    });

    // mousemove — throttled to at most once per second
    let _lastMove = 0;
    _map.on("mousemove", (e) => {
      const now = Date.now();
      if (now - _lastMove < 1000) return;
      _lastMove = now;
      const center = _map.getCenter();
      this.pushEvent("map-event", {
        event: "mousemove",
        latLng: [e.latlng.lat, e.latlng.lng],
        center: [center.lat, center.lng],
        zoom: _map.getZoom(),
      });
    });
  },
};

// ---------------------------------------------------------------------------
// Marker events pushed to the server.
// "drag" and "move" are excluded — they fire on every animation frame.
// ---------------------------------------------------------------------------

const MARKER_EVENTS = [
  "click", "dblclick", "contextmenu",
  "mouseover", "mouseout", "mousedown", "mouseup",
  "dragstart", "dragend",
  "popupopen", "popupclose",
  "tooltipopen", "tooltipclose",
];

// ---------------------------------------------------------------------------
// DMarkItem — one hook per stream sentinel <div>
//   mounted()   → add a Leaflet marker and wire all marker events
//   updated()   → move the Leaflet marker to new lat/lng
//   destroyed() → remove the Leaflet marker
// ---------------------------------------------------------------------------

window.Hooks.DMarkItem = {
  mounted() {
    if (!_map) return;
    const { name, lat, lng } = this.el.dataset;
    const domId = this.el.id;

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
      draggable: true,
    })
      .addTo(_map)
      .bindTooltip(name, { permanent: false, direction: "top" });

    // Wire all marker events
    MARKER_EVENTS.forEach((evtName) => {
      marker.on(evtName, () => {
        const ll = marker.getLatLng();
        this.pushEvent("marker-event", {
          event: evtName,
          id: domId,
          name,
          latLng: [ll.lat, ll.lng],
        });
      });
    });

    _markers.set(domId, marker);
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
