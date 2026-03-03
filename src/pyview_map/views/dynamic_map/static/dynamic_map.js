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

// Shared Leaflet map instance and marker registry.
// DynamicMap hook (the map <div>) writes _map once on mount.
// DMarkItem hooks (the invisible stream sentinels) read it.
let _map = null;
let _repeatedMarkers = null; // L.gridLayer.repeatedMarkers — handles world-copy duplication
const _markers = new Map(); // dom_id -> L.Marker (original; plugin manages copies)
const _polylines = new Map(); // dom_id -> L.Polyline

// Follow-marker: when set, DMarkItem.updated() auto-pans the map to this
// marker.  This avoids the handleEvent rendering issue where setView changes
// are not painted until mouse interaction.
let _followMarkerId = null; // dom_id of marker to follow, e.g. "markers-plane1"

// Hooks that mounted before the map was ready queue themselves here.
// DynamicMap.mounted() flushes them once _map is initialised.
const _pending = []; // Array of { el, hookCtx }
const _pendingPolylines = []; // Array of { el, hookCtx }

// ---------------------------------------------------------------------------
// Icon registry — parsed from the data-icon-registry attribute on #dmap
// ---------------------------------------------------------------------------
let _iconRegistry = null;

function _getIconRegistry() {
  if (_iconRegistry) return _iconRegistry;
  const el = document.getElementById("dmap");
  if (el && el.dataset.iconRegistry) {
    try { _iconRegistry = JSON.parse(el.dataset.iconRegistry); } catch (_) { _iconRegistry = {}; }
  } else {
    _iconRegistry = {};
  }
  return _iconRegistry;
}

const _FALLBACK_ICON_DEF = {
  html: `<div style="background:#2563eb;border:2px solid #fff;border-radius:50%;width:12px;height:12px;box-shadow:0 1px 3px rgba(0,0,0,.4)"></div>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6],
  className: "",
};

// Build a DivIcon, optionally baking heading rotation into the HTML so that
// copies created by Leaflet.RepeatedMarkers inherit the transform.
function _makeIcon(iconName, heading) {
  const reg = _getIconRegistry();
  const def = reg[iconName] || reg["default"] || _FALLBACK_ICON_DEF;
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

function _addMarkerFromEl(el, hookCtx) {
  const { name, lat, lng } = el.dataset;
  const iconName = el.dataset.icon || "default";
  const heading = el.dataset.heading;
  const speed = el.dataset.speed;
  const domId = el.id;

  // Guard: PyView's Stream.insert(update_only=True) doesn't transmit the
  // flag over the wire, so the client may fire mounted() for an item that
  // already exists.  Treat as an in-place update instead of adding a duplicate.
  if (_markers.has(domId)) {
    const marker = _markers.get(domId);
    const icon = _makeIcon(iconName, heading);
    marker.setLatLng([parseFloat(lat), parseFloat(lng)]);
    marker.setIcon(icon);
    marker.options.dmarkIcon = iconName;
    marker.options.dmarkHeading = heading;
    marker.options.dmarkSpeed = speed;
    const stampId = L.stamp(marker);
    for (const key in _repeatedMarkers._markersByTile) {
      const copy = _repeatedMarkers._markersByTile[key][stampId];
      if (copy) {
        const offset = _repeatedMarkers._offsetsByTile[key];
        copy.setLatLng([parseFloat(lat), parseFloat(lng) + offset]);
        copy.setIcon(_makeIcon(iconName, heading));
      }
    }
    return;
  }

  const icon = _makeIcon(iconName, heading);

  // Create marker but do NOT add to _map — the RepeatedMarkers layer
  // handles rendering in every visible world copy.
  const marker = L.marker([parseFloat(lat), parseFloat(lng)], {
    icon,
    dmarkName: name,
    dmarkIcon: iconName,
    dmarkHeading: heading,
    dmarkSpeed: speed,
    draggable: true,
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

  _repeatedMarkers.addMarker(marker);
  _markers.set(domId, marker);
  _log("add", `＋ ${name} appeared`);
}

// ---------------------------------------------------------------------------
// Polyline support — unwrap path so lines cross the antimeridian continuously
// ---------------------------------------------------------------------------

const POLYLINE_EVENTS = ["click", "dblclick", "contextmenu", "mouseover", "mouseout"];

// Unwrap longitudes so polylines crossing the antimeridian (±180°) take the
// short path instead of wrapping the long way around the globe.  Coordinates
// may extend beyond [-180, 180] — that's intentional; the repeated markers
// ensure there's always a visible marker at each endpoint.
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

function _addPolylineFromEl(el, hookCtx) {
  const { name } = el.dataset;
  const domId = el.id;
  const path = _unwrapPath(JSON.parse(el.dataset.path));
  const opts = _parsePolylineOpts(el);

  const polyline = L.polyline(path, opts)
    .addTo(_map)
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

  _polylines.set(domId, polyline);
  _log("add", `＋ polyline "${name}" added`);
}

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
];

window.Hooks.DynamicMap = {
  mounted() {
    _map = L.map(this.el).setView([39.5, -98.35], 4);

    // Repeated markers layer — renders marker copies in every world copy
    _repeatedMarkers = L.gridLayer.repeatedMarkers().addTo(_map);

    // Flush any DMarkItem hooks that mounted before _map was ready
    while (_pending.length) {
      const { el, hookCtx } = _pending.shift();
      _addMarkerFromEl(el, hookCtx);
    }
    // Flush any DPolylineItem hooks that mounted before _map was ready
    while (_pendingPolylines.length) {
      const { el, hookCtx } = _pendingPolylines.shift();
      _addPolylineFromEl(el, hookCtx);
    }
    L.tileLayer("http://{s}.tile.osm.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(_map);

    // Day/night terminator — updates every minute as the sun moves
    const terminator = L.terminator({ fillOpacity: 0.25 }).addTo(_map);
    setInterval(() => terminator.setTime(new Date()), 60_000);

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

    // -- Map command handlers from server push_event -------------------------
    this.handleEvent("setView", ({latLng, zoom}) => _map.setView(latLng, zoom));
    this.handleEvent("panTo", ({latLng}) => {
      _map.setView(latLng, _map.getZoom(), {animate: false});
    });
    this.handleEvent("followMarker", ({id}) => {
      _followMarkerId = id ? `markers-${id}` : null;
    });
    this.handleEvent("unfollowMarker", () => {
      _followMarkerId = null;
    });
    this.handleEvent("flyTo", ({latLng, zoom}) => _map.flyTo(latLng, zoom));
    this.handleEvent("fitBounds", ({corner1, corner2}) => _map.fitBounds([corner1, corner2]));
    this.handleEvent("flyToBounds", ({corner1, corner2}) => _map.flyToBounds([corner1, corner2]));
    this.handleEvent("setZoom", ({zoom}) => _map.setZoom(zoom));
    this.handleEvent("resetView", () => _map.setView([39.5, -98.35], 4));
    this.handleEvent("highlightMarker", ({id}) => {
      const marker = _markers.get(`markers-${id}`);
      if (marker) { _map.panTo(marker.getLatLng()); }
    });
    this.handleEvent("highlightPolyline", ({id}) => {
      const polyline = _polylines.get(`polylines-${id}`);
      if (polyline) { _map.fitBounds(polyline.getBounds()); polyline.openTooltip(); }
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
//   mounted()   → add marker to RepeatedMarkers layer
//   updated()   → update marker position/icon, redraw layer
//   destroyed() → remove from layer
// ---------------------------------------------------------------------------

window.Hooks.DMarkItem = {
  mounted() {
    if (!_map) {
      // Map not ready yet — queue for flush in DynamicMap.mounted()
      _pending.push({ el: this.el, hookCtx: this });
      return;
    }
    _addMarkerFromEl(this.el, this);
  },

  updated() {
    const marker = _markers.get(this.el.id);
    if (!marker) return;
    const lat = parseFloat(this.el.dataset.lat);
    const lng = parseFloat(this.el.dataset.lng);
    const newIcon = this.el.dataset.icon || "default";
    const heading = this.el.dataset.heading;
    const speed = this.el.dataset.speed;
    const icon = _makeIcon(newIcon, heading);

    // Update the master marker in place
    marker.setLatLng([lat, lng]);
    marker.setIcon(icon);
    marker.options.dmarkIcon = newIcon;
    marker.options.dmarkHeading = heading;
    marker.options.dmarkSpeed = speed;

    // Update all tile copies in place — avoids the remove/add cycle that
    // races with tile recreation triggered by panTo/setView.
    const stampId = L.stamp(marker);
    for (const key in _repeatedMarkers._markersByTile) {
      const copy = _repeatedMarkers._markersByTile[key][stampId];
      if (copy) {
        const offset = _repeatedMarkers._offsetsByTile[key];
        copy.setLatLng([lat, lng + offset]);
        copy.setIcon(_makeIcon(newIcon, heading));
        if (marker._tooltip) {
          if (copy._tooltip) copy.unbindTooltip();
          copy.bindTooltip(marker._tooltip._content, marker._tooltip.options);
        }
      }
    }
    // Auto-pan if this marker is being followed
    if (this.el.id === _followMarkerId) {
      _map.setView([lat, lng], _map.getZoom(), {animate: false});
    }

    _log("update", `→ ${marker.options.dmarkName} moved`);
  },

  destroyed() {
    const marker = _markers.get(this.el.id);
    if (!marker) return;
    const name = marker.options.dmarkName;
    _repeatedMarkers.removeMarker(marker);
    _markers.delete(this.el.id);
    _log("delete", `✕ ${name} removed`);
  },
};

// ---------------------------------------------------------------------------
// DPolylineItem — one hook per polyline stream sentinel <div>
// ---------------------------------------------------------------------------

window.Hooks.DPolylineItem = {
  mounted() {
    if (!_map) {
      _pendingPolylines.push({ el: this.el, hookCtx: this });
      return;
    }
    _addPolylineFromEl(this.el, this);
  },

  updated() {
    const polyline = _polylines.get(this.el.id);
    if (!polyline) return;
    const path = _unwrapPath(JSON.parse(this.el.dataset.path));
    polyline.setLatLngs(path);
    polyline.setStyle(_parsePolylineOpts(this.el));
    _log("update", `→ polyline "${this.el.dataset.name}" updated`);
  },

  destroyed() {
    const polyline = _polylines.get(this.el.id);
    if (!polyline) return;
    const name = this.el.dataset.name;
    polyline.remove();
    _polylines.delete(this.el.id);
    _log("delete", `✕ polyline "${name}" removed`);
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
