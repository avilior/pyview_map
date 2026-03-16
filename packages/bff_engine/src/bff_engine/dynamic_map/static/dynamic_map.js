// ---------------------------------------------------------------------------
// Leaflet.RepeatedMarkers patches
//
// The plugin has several bugs that cause ghost markers:
//   1) _addOffsetMarker copies _popup but not _tooltip
//   2) removeMarker never splices from _masterMarkers
//   3) createTile uses push() (sequential) but removeMarker uses L.stamp()
//   4) _removeTile iterates with for(i=0;i<length;i++) which fails on
//      stamp-indexed sparse arrays — copies are never removed from the map
//
// We use plain objects {} instead of arrays for _markersByTile entries so
// that all iteration (removeMarker, _removeTile, in-place updates) works
// correctly with stamp-based keys.
// ---------------------------------------------------------------------------

// 1) Copy _tooltip to copies (plugin only copies _popup).
const _origAddOffset = L.GridLayer.RepeatedMarkers.prototype._addOffsetMarker;
L.GridLayer.RepeatedMarkers.prototype._addOffsetMarker = function(marker, longitudeOffset) {
  const copy = _origAddOffset.call(this, marker, longitudeOffset);
  if (marker._tooltip) {
    copy.bindTooltip(marker._tooltip._content, marker._tooltip.options);
  }
  return copy;
};

// 2) Fix removeMarker to actually splice from _masterMarkers.
L.GridLayer.RepeatedMarkers.prototype.removeMarker = function(marker) {
  var i = this._masterMarkers.indexOf(marker);
  if (i === -1) return false;
  this._masterMarkers.splice(i, 1);
  var masterMarkerId = L.stamp(marker);
  for (var key in this._markersByTile) {
    var copy = this._markersByTile[key][masterMarkerId];
    if (copy && this._map) copy.remove();
    delete this._markersByTile[key][masterMarkerId];
  }
};

// 3) Fix createTile to use stamp-based indexing with plain objects.
L.GridLayer.RepeatedMarkers.prototype.createTile = function(coords) {
  var key = this._tileCoordsToKey(coords);
  var longitudeOffset = coords.x * 360;
  this._markersByTile[key] = {};            // plain object, not array
  this._offsetsByTile[key] = longitudeOffset;
  for (var i = 0, l = this._masterMarkers.length; i < l; i++) {
    var marker = this._masterMarkers[i];
    this._markersByTile[key][L.stamp(marker)] = this._addOffsetMarker(marker, longitudeOffset);
  }
  return L.DomUtil.create("div");
};

// 4) Fix _removeTile to iterate stamp-keyed objects instead of sequential arrays.
L.GridLayer.RepeatedMarkers.prototype._removeTile = function(key) {
  var copies = this._markersByTile[key];
  if (copies) {
    for (var stampId in copies) {
      if (copies[stampId] && this._map) {
        copies[stampId].removeFrom(this._map);
      }
    }
  }
  delete this._markersByTile[key];
  delete this._offsetsByTile[key];
  L.GridLayer.prototype._removeTile.call(this, key);
};

// ---------------------------------------------------------------------------
// MapInstance — per-map state container
//
// Each DynamicMap hook creates a MapInstance. DMarkItem / DPolylineItem hooks
// find their instance via closest('[data-channel]').
// ---------------------------------------------------------------------------

class MapInstance {
  constructor(channel) {
    this.channel = channel;
    this.map = null;
    this.repeatedMarkers = null;
    this.markers = new Map();     // dom_id -> L.Marker
    this.polylines = new Map();   // dom_id -> L.Polyline
    this.followMarkerId = null;   // dom_id of marker to follow
    this.pendingMarkers = [];     // queued DMarkItem hooks before map ready
    this.pendingPolylines = [];   // queued DPolylineItem hooks before map ready
    this.iconRegistry = null;
  }

  getIconRegistry() {
    if (this.iconRegistry) return this.iconRegistry;
    const el = document.getElementById(this.channel);
    if (el && el.dataset.iconRegistry) {
      try { this.iconRegistry = JSON.parse(el.dataset.iconRegistry); } catch (_) { this.iconRegistry = {}; }
    } else {
      this.iconRegistry = {};
    }
    return this.iconRegistry;
  }
}

// Global registry of MapInstance objects, keyed by the component ID.
const _instances = new Map();

const _FALLBACK_ICON_DEF = {
  html: `<div style="background:#2563eb;border:2px solid #fff;border-radius:50%;width:12px;height:12px;box-shadow:0 1px 3px rgba(0,0,0,.4)"></div>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6],
  className: "",
};

// Build a DivIcon, optionally baking heading rotation into the HTML so that
// copies created by Leaflet.RepeatedMarkers inherit the transform.
//
// If iconName is found in the registry, use that definition.
// Otherwise treat iconName as literal HTML/emoji content (e.g. "🌋", "<svg>…</svg>")
// and wrap it in a centered div.
function _makeIcon(instance, iconName, heading) {
  const reg = instance.getIconRegistry();
  const regEntry = reg[iconName];
  let def;
  if (regEntry) {
    def = regEntry;
  } else if (iconName && iconName !== "default") {
    // Literal icon content — wrap in a centered container
    def = {
      html: `<div style="display:flex;align-items:center;justify-content:center;font-size:20px;width:28px;height:28px">${iconName}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      className: "",
    };
  } else {
    def = reg["default"] || _FALLBACK_ICON_DEF;
  }
  let html = def.html;
  if (heading != null && heading !== "" && heading !== "None") {
    html = `<div style="transform:rotate(${heading}deg);transform-origin:center center;transition:transform 0.3s ease">${html}</div>`;
  }
  return L.divIcon({
    className: def.className ?? "",
    html,
    iconSize: def.iconSize,
    iconAnchor: def.iconAnchor,
  });
}

// ---------------------------------------------------------------------------
// Find the MapInstance for a hook element by walking up to the nearest
// [data-channel] ancestor.
// ---------------------------------------------------------------------------

function _findInstance(el) {
  const wrapper = el.closest("[data-channel]");
  if (!wrapper) return null;
  return _instances.get(wrapper.dataset.channel) || null;
}

// ---------------------------------------------------------------------------
// Marker / polyline helpers
// ---------------------------------------------------------------------------

function _addMarkerFromEl(instance, el, hookCtx) {
  const { name, lat, lng } = el.dataset;
  const iconName = el.dataset.icon || "default";
  const heading = el.dataset.heading;
  const speed = el.dataset.speed;
  const domId = el.id;

  // Guard: PyView's Stream.insert(update_only=True) doesn't transmit the
  // flag over the wire, so the client may fire mounted() for an item that
  // already exists.  Treat as an in-place update instead of adding a duplicate.
  if (instance.markers.has(domId)) {
    const marker = instance.markers.get(domId);
    const icon = _makeIcon(instance, iconName, heading);
    marker.setLatLng([parseFloat(lat), parseFloat(lng)]);
    marker.setIcon(icon);
    marker.options.dmarkIcon = iconName;
    marker.options.dmarkHeading = heading;
    marker.options.dmarkSpeed = speed;
    const stampId = L.stamp(marker);
    for (const key in instance.repeatedMarkers._markersByTile) {
      const copy = instance.repeatedMarkers._markersByTile[key][stampId];
      if (copy) {
        const offset = instance.repeatedMarkers._offsetsByTile[key];
        copy.setLatLng([parseFloat(lat), parseFloat(lng) + offset]);
        copy.setIcon(_makeIcon(instance, iconName, heading));
      }
    }
    return;
  }

  const icon = _makeIcon(instance, iconName, heading);

  // Create marker but do NOT add to _map — the RepeatedMarkers layer
  // handles rendering in every visible world copy.
  const marker = L.marker([parseFloat(lat), parseFloat(lng)], {
    icon,
    dmarkName: name,
    dmarkIcon: iconName,
    dmarkHeading: heading,
    dmarkSpeed: speed,
  })
    .bindTooltip(name, { permanent: false, direction: "top" });

  MARKER_EVENTS.forEach((evtName) => {
    marker.on(evtName, () => {
      const ll = marker.getLatLng();
      hookCtx.pushEvent("marker-event", {
        event: evtName,
        id: domId,
        name,
        latLng: [ll.lat, ll.lng],
      });
    });
  });

  instance.repeatedMarkers.addMarker(marker);
  instance.markers.set(domId, marker);
  _log(instance, "add", `＋ ${name} appeared`);
}

// ---------------------------------------------------------------------------
// Polyline support — unwrap path so lines cross the antimeridian continuously
// ---------------------------------------------------------------------------

const POLYLINE_EVENTS = ["click", "dblclick", "contextmenu", "mouseover", "mouseout"];

function _unwrapPath(path) {
  if (path.length < 2) return path;
  const result = [[path[0][0], path[0][1]]];
  for (let i = 1; i < path.length; i++) {
    const prevLng = result[i - 1][1];
    let lng = path[i][1];
    while (lng - prevLng > 180) lng -= 360;
    while (lng - prevLng < -180) lng += 360;
    result.push([path[i][0], lng]);
  }
  return result;
}

function _parsePolylineOpts(el) {
  const opts = {
    color: el.dataset.color || "#3388ff",
    weight: parseInt(el.dataset.weight) || 3,
    opacity: parseFloat(el.dataset.opacity) || 1.0,
  };
  const dashArray = el.dataset.dashArray;
  if (dashArray && dashArray !== "None" && dashArray !== "null") {
    opts.dashArray = dashArray;
  }
  return opts;
}

function _addPolylineFromEl(instance, el, hookCtx) {
  const { name } = el.dataset;
  const domId = el.id;
  const path = _unwrapPath(JSON.parse(el.dataset.path));
  const opts = _parsePolylineOpts(el);

  const polyline = L.polyline(path, opts)
    .addTo(instance.map)
    .bindTooltip(name, { sticky: true });

  POLYLINE_EVENTS.forEach((evtName) => {
    polyline.on(evtName, (e) => {
      const ll = e.latlng;
      hookCtx.pushEvent("polyline-event", {
        event: evtName,
        id: domId,
        name,
        latLng: [ll.lat, ll.lng],
      });
    });
  });

  instance.polylines.set(domId, polyline);
  _log(instance, "add", `＋ polyline "${name}" added`);
}

// ---------------------------------------------------------------------------
// DynamicMap — initialises the Leaflet map and wires all map-level events
// ---------------------------------------------------------------------------

window.Hooks = window.Hooks ?? {};

// Map events pushed to the server (with their payload builders).
const MAP_EVENTS = [
  "click", "dblclick", "contextmenu",
  "mouseover", "mouseout",
  "moveend", "zoomend", "zoomlevelschange", "resize",
  "locationfound", "locationerror",
  "popupopen", "popupclose",
  "tooltipopen", "tooltipclose",
];

window.Hooks.DynamicMap = {
  mounted() {
    // Re-use an existing MapInstance if DMarkItem/DPolylineItem hooks already
    // created one (they mount before DynamicMap and queue pending items).
    let instance = _instances.get(this.el.id);
    if (!instance) {
      instance = new MapInstance(this.el.id);
      _instances.set(this.el.id, instance);
    }

    instance.map = L.map(this.el).setView([39.5, -98.35], 4);

    // Repeated markers layer — renders marker copies in every world copy
    instance.repeatedMarkers = L.gridLayer.repeatedMarkers().addTo(instance.map);

    // Flush any DMarkItem hooks that mounted before the map was ready
    while (instance.pendingMarkers.length) {
      const { el, hookCtx } = instance.pendingMarkers.shift();
      _addMarkerFromEl(instance, el, hookCtx);
    }
    // Flush any DPolylineItem hooks that mounted before the map was ready
    while (instance.pendingPolylines.length) {
      const { el, hookCtx } = instance.pendingPolylines.shift();
      _addPolylineFromEl(instance, el, hookCtx);
    }

    L.tileLayer("http://{s}.tile.osm.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(instance.map);

    // Day/night terminator — updates every minute as the sun moves
    const terminator = L.terminator({ fillOpacity: 0.25 }).addTo(instance.map);
    setInterval(() => terminator.setTime(new Date()), 60_000);

    // Wire all low-frequency map events
    const channel = instance.channel;
    MAP_EVENTS.forEach((evtName) => {
      instance.map.on(evtName, (e) => {
        const center = instance.map.getCenter();
        const bounds = instance.map.getBounds();
        this.pushEvent("map-event", {
          event: evtName,
          latLng: e.latlng ? [e.latlng.lat, e.latlng.lng] : null,
          center: [center.lat, center.lng],
          zoom: instance.map.getZoom(),
          bounds: [[bounds.getSouthWest().lat, bounds.getSouthWest().lng],
                   [bounds.getNorthEast().lat, bounds.getNorthEast().lng]],
        });
      });
    });

    // -- Map command handlers from server push_event -------------------------
    // Events are namespaced with channel to prevent leaking between instances.
    this.handleEvent(`${channel}:setView`, ({latLng, zoom}) => instance.map.setView(latLng, zoom));
    this.handleEvent(`${channel}:panTo`, ({latLng}) => {
      instance.map.setView(latLng, instance.map.getZoom(), {animate: false});
    });
    this.handleEvent(`${channel}:followMarker`, ({id}) => {
      instance.followMarkerId = id ? `${channel}-markers-${id}` : null;
    });
    this.handleEvent(`${channel}:unfollowMarker`, () => {
      instance.followMarkerId = null;
    });
    this.handleEvent(`${channel}:flyTo`, ({latLng, zoom}) => instance.map.flyTo(latLng, zoom));
    this.handleEvent(`${channel}:fitBounds`, ({corner1, corner2}) => instance.map.fitBounds([corner1, corner2]));
    this.handleEvent(`${channel}:flyToBounds`, ({corner1, corner2}) => instance.map.flyToBounds([corner1, corner2]));
    this.handleEvent(`${channel}:setZoom`, ({zoom}) => instance.map.setZoom(zoom));
    this.handleEvent(`${channel}:resetView`, () => instance.map.setView([39.5, -98.35], 4));
    this.handleEvent(`${channel}:highlightMarker`, ({id}) => {
      const marker = instance.markers.get(`${channel}-markers-${id}`);
      if (marker) { instance.map.panTo(marker.getLatLng()); }
    });
    this.handleEvent(`${channel}:highlightPolyline`, ({id}) => {
      const polyline = instance.polylines.get(`${channel}-polylines-${id}`);
      if (polyline) { instance.map.fitBounds(polyline.getBounds()); polyline.openTooltip(); }
    });

    // mousemove — throttled to at most once per second
    let _lastMove = 0;
    instance.map.on("mousemove", (e) => {
      const now = Date.now();
      if (now - _lastMove < 1000) return;
      _lastMove = now;
      const center = instance.map.getCenter();
      const bounds = instance.map.getBounds();
      this.pushEvent("map-event", {
        event: "mousemove",
        latLng: [e.latlng.lat, e.latlng.lng],
        center: [center.lat, center.lng],
        zoom: instance.map.getZoom(),
        bounds: [[bounds.getSouthWest().lat, bounds.getSouthWest().lng],
                 [bounds.getNorthEast().lat, bounds.getNorthEast().lng]],
      });
    });

    this.pushEvent("map-ready", {});
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
//   mounted()   → add marker to RepeatedMarkers layer
//   updated()   → update marker position/icon, redraw layer
//   destroyed() → remove from layer
// ---------------------------------------------------------------------------

window.Hooks.DMarkItem = {
  mounted() {
    const instance = _findInstance(this.el);
    if (!instance || !instance.map) {
      // Map not ready yet — find or create a pending instance and queue
      const wrapper = this.el.closest("[data-channel]");
      if (wrapper) {
        const ch = wrapper.dataset.channel;
        let inst = _instances.get(ch);
        if (!inst) {
          inst = new MapInstance(ch);
          _instances.set(ch, inst);
        }
        inst.pendingMarkers.push({ el: this.el, hookCtx: this });
      }
      return;
    }
    _addMarkerFromEl(instance, this.el, this);
  },

  updated() {
    const instance = _findInstance(this.el);
    if (!instance) return;
    const marker = instance.markers.get(this.el.id);
    if (!marker) return;
    const lat = parseFloat(this.el.dataset.lat);
    const lng = parseFloat(this.el.dataset.lng);
    const newIcon = this.el.dataset.icon || "default";
    const heading = this.el.dataset.heading;
    const speed = this.el.dataset.speed;
    const icon = _makeIcon(instance, newIcon, heading);

    // Update the master marker in place
    marker.setLatLng([lat, lng]);
    marker.setIcon(icon);
    marker.options.dmarkIcon = newIcon;
    marker.options.dmarkHeading = heading;
    marker.options.dmarkSpeed = speed;

    // Update all tile copies in place
    const stampId = L.stamp(marker);
    for (const key in instance.repeatedMarkers._markersByTile) {
      const copy = instance.repeatedMarkers._markersByTile[key][stampId];
      if (copy) {
        const offset = instance.repeatedMarkers._offsetsByTile[key];
        copy.setLatLng([lat, lng + offset]);
        copy.setIcon(_makeIcon(instance, newIcon, heading));
        if (marker._tooltip) {
          if (copy._tooltip) copy.unbindTooltip();
          copy.bindTooltip(marker._tooltip._content, marker._tooltip.options);
        }
      }
    }
    // Auto-pan if this marker is being followed
    if (this.el.id === instance.followMarkerId) {
      instance.map.setView([lat, lng], instance.map.getZoom(), {animate: false});
    }

    _log(instance, "update", `→ ${marker.options.dmarkName} moved`);
  },

  destroyed() {
    const instance = _findInstance(this.el);
    if (!instance) return;
    const marker = instance.markers.get(this.el.id);
    if (!marker) return;
    const name = marker.options.dmarkName;
    instance.repeatedMarkers.removeMarker(marker);
    instance.markers.delete(this.el.id);
    _log(instance, "delete", `✕ ${name} removed`);
  },
};

// ---------------------------------------------------------------------------
// DPolylineItem — one hook per polyline stream sentinel <div>
// ---------------------------------------------------------------------------

window.Hooks.DPolylineItem = {
  mounted() {
    const instance = _findInstance(this.el);
    if (!instance || !instance.map) {
      const wrapper = this.el.closest("[data-channel]");
      if (wrapper) {
        const ch = wrapper.dataset.channel;
        let inst = _instances.get(ch);
        if (!inst) {
          inst = new MapInstance(ch);
          _instances.set(ch, inst);
        }
        inst.pendingPolylines.push({ el: this.el, hookCtx: this });
      }
      return;
    }
    _addPolylineFromEl(instance, this.el, this);
  },

  updated() {
    const instance = _findInstance(this.el);
    if (!instance) return;
    const polyline = instance.polylines.get(this.el.id);
    if (!polyline) return;
    const path = _unwrapPath(JSON.parse(this.el.dataset.path));
    polyline.setLatLngs(path);
    polyline.setStyle(_parsePolylineOpts(this.el));
    _log(instance, "update", `→ polyline "${this.el.dataset.name}" updated`);
  },

  destroyed() {
    const instance = _findInstance(this.el);
    if (!instance) return;
    const polyline = instance.polylines.get(this.el.id);
    if (!polyline) return;
    const name = this.el.dataset.name;
    polyline.remove();
    instance.polylines.delete(this.el.id);
    _log(instance, "delete", `✕ polyline "${name}" removed`);
  },
};

// ---------------------------------------------------------------------------
// Activity log helper
// ---------------------------------------------------------------------------

function _log(instance, type, message) {
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
