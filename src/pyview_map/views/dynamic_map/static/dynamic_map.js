// ---------------------------------------------------------------------------
// DynamicMap — Leaflet wrapper that tracks dmarks by id
// ---------------------------------------------------------------------------

class DynamicMap {
  constructor(element, center, zoom) {
    this.map = L.map(element).setView(center, zoom);
    this.markers = new Map(); // id -> L.Marker

    L.tileLayer("http://{s}.tile.osm.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(this.map);
  }

  addMarker(dmark) {
    if (this.markers.has(dmark.id)) return;

    const icon = L.divIcon({
      className: "",
      html: `<div style="
        background:#2563eb;border:2px solid #fff;border-radius:50%;
        width:12px;height:12px;box-shadow:0 1px 3px rgba(0,0,0,.4)">
      </div>`,
      iconSize: [12, 12],
      iconAnchor: [6, 6],
    });

    const marker = L.marker(dmark.latLng, {
      icon,
      dmarkId: dmark.id,
      dmarkName: dmark.name,
    })
      .addTo(this.map)
      .bindTooltip(dmark.name, { permanent: false, direction: "top" });

    this.markers.set(dmark.id, marker);
  }

  removeMarker(id) {
    const marker = this.markers.get(id);
    if (!marker) return;
    marker.remove();
    this.markers.delete(id);
  }

  moveMarker(id, latLng) {
    const marker = this.markers.get(id);
    if (!marker) return;
    marker.setLatLng(latLng);
  }

  getName(id) {
    const marker = this.markers.get(id);
    return marker ? marker.options.dmarkName : id;
  }
}

// ---------------------------------------------------------------------------
// PyView hook
// ---------------------------------------------------------------------------

window.Hooks = window.Hooks ?? {};

window.Hooks.DynamicMap = {
  mounted() {
    // Centred on the continental US
    this.dmap = new DynamicMap(this.el, [39.5, -98.35], 4);

    const initial = JSON.parse(this.el.dataset.markers);
    initial.forEach((m) => this.dmap.addMarker(m));

    // ── server → client events ──────────────────────────────────────────

    this.handleEvent("dmarker-add", (data) => {
      this.dmap.addMarker(data);
      this._log("add", `＋ ${data.name} appeared`);
    });

    this.handleEvent("dmarker-delete", (data) => {
      const name = this.dmap.getName(data.id);
      this.dmap.removeMarker(data.id);
      this._log("delete", `✕ ${name} removed`);
    });

    this.handleEvent("dmarker-update", (data) => {
      const name = this.dmap.getName(data.id);
      this.dmap.moveMarker(data.id, data.latLng);
      this._log("update", `→ ${name} moved`);
    });
  },

  // ── activity log ────────────────────────────────────────────────────────

  _log(type, message) {
    const log = document.getElementById("dmap-log");
    if (!log) return;

    const entry = document.createElement("div");
    entry.className = `log-${type}`;
    const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    entry.textContent = `${ts}  ${message}`;
    log.prepend(entry);

    // Cap the log at 60 entries
    while (log.children.length > 60) {
      log.removeChild(log.lastChild);
    }
  },
};
