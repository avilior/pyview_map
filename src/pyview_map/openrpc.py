"""OpenRPC spec generation and documentation endpoints for JSON-RPC services.

Provides:
- generate_openrpc() — builds an OpenRPC 1.3.2 document from a JRPCService
- setup_rpc_docs() — one-call setup: registers rpc.discover, adds /openrpc.json and /docs routes
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from http_stream_transport.jsonrpc.jrpc_service import JRPCService
from http_stream_transport.jsonrpc.handler_meta import MethodRecord


def generate_openrpc(
    service: JRPCService, *, title: str, version: str = "1.0.0", description: str = ""
) -> dict[str, Any]:
    """Build an OpenRPC 1.3.2 document from registered JRPC methods."""
    # Skip internal MCP lifecycle methods and rpc.discover itself
    _skip = {"rpc.discover", "initialize", "notifications/initialized"}
    methods = []
    for name, record in service.registered_methods().items():
        if name in _skip:
            continue
        methods.append(_method_object(record))

    doc: dict[str, Any] = {"openrpc": "1.3.2", "info": {"title": title, "version": version}, "methods": methods}
    if description:
        doc["info"]["description"] = description
    return doc


def _method_object(record: MethodRecord) -> dict[str, Any]:
    """Convert a MethodRecord to an OpenRPC Method Object."""
    method: dict[str, Any] = {"name": record.name}

    if record.docstring:
        lines = record.docstring.strip().splitlines()
        method["summary"] = lines[0].strip()
        if len(lines) > 1:
            method["description"] = record.docstring.strip()

    method["params"] = _params_from_schema(record.param_schema)

    # Mark streaming methods (return asyncio.Queue → SSE)
    is_streaming = record.handler_meta.return_type is asyncio.Queue
    if is_streaming:
        method["x-streaming"] = True
        method["result"] = {"name": "result", "schema": {"type": "object", "description": "SSE event stream"}}
    elif record.return_schema:
        method["result"] = {"name": "result", "schema": record.return_schema}
    else:
        method["result"] = {"name": "result", "schema": {"type": "null"}}

    # Tags for namespace grouping
    if "." in record.name:
        namespace = record.name.rsplit(".", 1)[0]
        method["tags"] = [{"name": namespace}]

    return method


# -- Schema helpers -----------------------------------------------------------


def _params_from_schema(param_schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Convert Pydantic JSON Schema to OpenRPC ContentDescriptor array."""
    if not param_schema:
        return []

    properties = param_schema.get("properties", {})
    required_set = set(param_schema.get("required", []))
    defs = param_schema.get("$defs", {})

    params = []
    for name, prop_schema in properties.items():
        resolved = _resolve_refs(prop_schema, defs)
        schema = {k: v for k, v in resolved.items() if k != "title"}
        params.append({"name": name, "required": name in required_set, "schema": schema})
    return params


def _resolve_refs(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Inline $ref references from $defs."""
    if "$ref" in schema:
        ref_path = schema["$ref"]
        if ref_path.startswith("#/$defs/"):
            def_name = ref_path[len("#/$defs/") :]
            if def_name in defs:
                return _resolve_refs(defs[def_name], defs)
        return schema

    result = dict(schema)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in result:
            result[key] = [_resolve_refs(s, defs) for s in result[key]]
    if "items" in result and isinstance(result["items"], dict):
        result["items"] = _resolve_refs(result["items"], defs)
    if "additionalProperties" in result and isinstance(result["additionalProperties"], dict):
        result["additionalProperties"] = _resolve_refs(result["additionalProperties"], defs)
    return result


# -- Route setup --------------------------------------------------------------


def setup_rpc_docs(
    app: FastAPI, service: JRPCService, *, title: str, version: str = "1.0.0", description: str = "", prefix: str = ""
) -> None:
    """One-call setup: registers rpc.discover, adds /openrpc.json and /docs routes.

    Args:
        app: FastAPI app to add routes to.
        service: JRPCService instance to introspect.
        title: Service title for the spec.
        version: Service version.
        description: Service description.
        prefix: Route prefix (e.g. "/api"). Leave empty for sub-apps already mounted.
    """
    _cache: dict[str, Any] = {}

    def _get_spec() -> dict[str, Any]:
        if "spec" not in _cache:
            _cache["spec"] = generate_openrpc(service, title=title, version=version, description=description)
        return _cache["spec"]

    @service.request("rpc.discover")
    def rpc_discover() -> dict:
        """Return the OpenRPC service discovery document."""
        return _get_spec()

    @app.get(f"{prefix}/openrpc.json")
    async def openrpc_spec():
        return JSONResponse(_get_spec())

    @app.get(f"{prefix}/docs", response_class=HTMLResponse)
    async def openrpc_docs():
        return _DOCS_HTML


# -- Self-contained HTML explorer ---------------------------------------------

_DOCS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JSON-RPC API</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#fff;--bg2:#f7f8fa;--bg3:#eef0f4;--text:#1a1a2e;--text2:#555;
  --border:#dde;--accent:#0055cc;--accent-bg:#e8f0fe;
  --green:#1a7f37;--red:#cf222e;--orange:#b35900;
  --mono:ui-monospace,'SF Mono','Cascadia Code','Consolas',monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --radius:6px;
}
body{font-family:var(--sans);color:var(--text);background:var(--bg);font-size:14px;line-height:1.5}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

/* Layout */
.wrapper{display:flex;min-height:100vh}
.sidebar{width:240px;border-right:1px solid var(--border);background:var(--bg2);
  overflow-y:auto;position:sticky;top:0;height:100vh;flex-shrink:0}
.main{flex:1;padding:24px 32px;max-width:900px}

/* Sidebar */
.sidebar-header{padding:16px;border-bottom:1px solid var(--border)}
.sidebar-header h1{font-size:16px;font-weight:700}
.sidebar-header .version{font-size:11px;color:var(--text2);background:var(--bg3);
  padding:1px 6px;border-radius:10px;margin-left:6px}
.sidebar-header .desc{font-size:12px;color:var(--text2);margin-top:4px}
.nav-group{padding:8px 0}
.nav-group-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
  color:var(--text2);padding:4px 16px}
.nav-item{display:block;padding:3px 16px 3px 24px;font-size:13px;font-family:var(--mono);
  color:var(--text);cursor:pointer;border-left:3px solid transparent}
.nav-item:hover{background:var(--bg3);text-decoration:none}
.nav-item.active{border-left-color:var(--accent);background:var(--accent-bg);font-weight:600}
.nav-item .method-short{color:var(--text2);font-family:var(--sans);font-size:11px;margin-left:4px}

/* Auth bar */
.auth-bar{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;
  align-items:center;gap:8px;font-size:12px}
.auth-bar label{color:var(--text2);white-space:nowrap}
.auth-bar input{flex:1;font-family:var(--mono);font-size:12px;padding:4px 8px;
  border:1px solid var(--border);border-radius:var(--radius);background:var(--bg)}

/* Method cards */
.method-card{border:1px solid var(--border);border-radius:var(--radius);margin-bottom:20px;
  background:var(--bg);scroll-margin-top:16px}
.method-header{padding:14px 16px;border-bottom:1px solid var(--border);background:var(--bg2)}
.method-name{font-family:var(--mono);font-size:15px;font-weight:700}
.method-name .ns{color:var(--text2)}
.badge{font-size:10px;font-weight:600;padding:2px 7px;border-radius:10px;margin-left:8px;
  vertical-align:middle;text-transform:uppercase;letter-spacing:.3px}
.badge-stream{background:#fff3cd;color:var(--orange)}
.method-summary{font-size:13px;color:var(--text2);margin-top:2px}
.method-body{padding:16px}

/* Params table */
.section-title{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
  color:var(--text2);margin-bottom:6px;margin-top:12px}
.section-title:first-child{margin-top:0}
.params-table{width:100%;border-collapse:collapse;font-size:13px}
.params-table th{text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.3px;color:var(--text2);padding:4px 10px;border-bottom:2px solid var(--border)}
.params-table td{padding:5px 10px;border-bottom:1px solid var(--border);vertical-align:top}
.params-table tr:last-child td{border-bottom:none}
.param-name{font-family:var(--mono);font-weight:600}
.param-type{font-family:var(--mono);font-size:12px;color:var(--accent)}
.param-req{font-size:11px;font-weight:600}
.param-req.yes{color:var(--green)}
.param-req.no{color:var(--text2)}
.param-default{font-family:var(--mono);font-size:12px;color:var(--text2)}
.return-type{font-family:var(--mono);font-size:13px;color:var(--accent)}

/* Try It */
.try-it{border-top:1px solid var(--border);margin-top:12px;padding-top:12px}
.try-toggle{font-size:12px;font-weight:600;color:var(--accent);cursor:pointer;
  user-select:none;display:flex;align-items:center;gap:4px}
.try-toggle .arrow{transition:transform .15s;display:inline-block}
.try-toggle.open .arrow{transform:rotate(90deg)}
.try-panel{display:none;margin-top:10px}
.try-panel.open{display:block}
.try-panel textarea{width:100%;font-family:var(--mono);font-size:12px;padding:10px;
  border:1px solid var(--border);border-radius:var(--radius);background:var(--bg2);
  resize:vertical;min-height:100px;line-height:1.4;tab-size:2}
.try-actions{display:flex;gap:8px;margin-top:8px;align-items:center}
.btn{font-size:12px;font-weight:600;padding:6px 14px;border-radius:var(--radius);
  border:1px solid transparent;cursor:pointer}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-primary:hover{opacity:.9}
.btn-secondary{background:var(--bg);color:var(--text);border-color:var(--border)}
.btn-secondary:hover{background:var(--bg2)}
.try-status{font-size:12px;color:var(--text2)}
.response-area{margin-top:10px}
.response-area pre{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);
  padding:10px;font-family:var(--mono);font-size:12px;overflow-x:auto;max-height:400px;
  overflow-y:auto;white-space:pre-wrap;word-break:break-word}
.response-area .resp-ok{border-left:3px solid var(--green)}
.response-area .resp-err{border-left:3px solid var(--red)}

/* Empty state */
.empty{text-align:center;padding:80px 20px;color:var(--text2)}
.empty h2{font-size:18px;margin-bottom:8px;color:var(--text)}

/* Responsive */
@media(max-width:768px){
  .sidebar{display:none}
  .main{padding:16px}
}
</style>
</head>
<body>
<div class="wrapper">
  <nav class="sidebar">
    <div class="sidebar-header">
      <h1 id="s-title"></h1>
      <div class="desc" id="s-desc"></div>
    </div>
    <div class="auth-bar">
      <label for="token">Token</label>
      <input id="token" type="text" placeholder="tok-acme-001" value="tok-acme-001">
    </div>
    <div id="s-nav"></div>
  </nav>
  <div class="main" id="content">
    <div class="empty"><h2>Loading&hellip;</h2></div>
  </div>
</div>
<script>
(function() {
  // -- State --
  let spec = null;
  let session = null;

  // -- MCP Session --
  class McpSession {
    constructor() { this.sid = null; this.nextId = 1; }

    async call(method, params) {
      const token = document.getElementById('token').value;
      if (!this.sid) await this._init(token);
      return this._rpc(method, params);
    }

    async _init(token) {
      const resp = await this._post({
        jsonrpc: '2.0', id: this.nextId++, method: 'initialize',
        params: { protocolVersion: '2025-03-26', capabilities: {},
                  clientInfo: { name: 'openrpc-explorer', version: '1.0' } },
      });
      this.sid = resp.headers.get('mcp-session-id');
      await this._post({ jsonrpc: '2.0', method: 'notifications/initialized' });
    }

    async _rpc(method, params) {
      const resp = await this._post({ jsonrpc: '2.0', id: this.nextId++, method, params });
      return this._parse(resp);
    }

    async _post(body) {
      const h = { 'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream' };
      const token = document.getElementById('token').value;
      if (token) h['Authorization'] = 'Bearer ' + token;
      if (this.sid) h['Mcp-Session-Id'] = this.sid;
      return fetch('./mcp', { method: 'POST', headers: h, body: JSON.stringify(body) });
    }

    async _parse(resp) {
      const ct = resp.headers.get('content-type') || '';
      const text = await resp.text();
      if (ct.includes('text/event-stream')) {
        const results = [];
        for (const line of text.split('\\n')) {
          if (line.startsWith('data: ')) {
            try { results.push(JSON.parse(line.slice(6))); } catch {}
          }
        }
        return results.length === 1 ? results[0] : results;
      }
      try { return JSON.parse(text); } catch { return text; }
    }

    reset() { this.sid = null; }
  }

  // -- Schema → human-readable type --
  function schemaType(s) {
    if (!s) return 'any';
    if (s.type === 'array') return schemaType(s.items) + '[]';
    if (s.type === 'object') return 'object';
    if (s.type) return s.type;
    if (s.anyOf) return s.anyOf.map(schemaType).join(' | ');
    if (s.oneOf) return s.oneOf.map(schemaType).join(' | ');
    return 'any';
  }

  // -- Build example params --
  function exampleValue(s) {
    if (!s) return null;
    if (s.default !== undefined) return s.default;
    if (s.type === 'string') return '';
    if (s.type === 'integer') return 0;
    if (s.type === 'number') return 0.0;
    if (s.type === 'boolean') return false;
    if (s.type === 'array') {
      if (s.items && s.items.type === 'array') return [[0, 0]];
      if (s.items && (s.items.type === 'number' || s.items.type === 'integer')) return [0, 0];
      return [];
    }
    if (s.type === 'object') return {};
    if (s.anyOf) {
      const nonNull = s.anyOf.find(x => x.type !== 'null');
      return nonNull ? exampleValue(nonNull) : null;
    }
    return null;
  }

  function buildExample(method) {
    const params = {};
    for (const p of method.params) {
      if (p.required) {
        params[p.name] = exampleValue(p.schema);
      } else if (p.schema.default !== undefined) {
        params[p.name] = p.schema.default;
      }
    }
    return { jsonrpc: '2.0', id: 1, method: method.name, params };
  }

  // -- Render --
  function render() {
    if (!spec) return;

    // Sidebar
    document.getElementById('s-title').innerHTML =
      esc(spec.info.title) + '<span class="version">v' + esc(spec.info.version) + '</span>';
    document.getElementById('s-desc').textContent = spec.info.description || '';

    // Group methods by namespace
    const groups = new Map();
    for (const m of spec.methods) {
      const ns = m.tags?.[0]?.name || '_root';
      if (!groups.has(ns)) groups.set(ns, []);
      groups.get(ns).push(m);
    }

    // Nav
    let nav = '';
    for (const [ns, methods] of groups) {
      nav += '<div class="nav-group"><div class="nav-group-title">' + esc(ns) + '</div>';
      for (const m of methods) {
        const short = m.name.split('.').pop();
        nav += '<a class="nav-item" href="#' + esc(m.name) + '">' + esc(short);
        if (m['x-streaming']) nav += ' <span class="method-short">SSE</span>';
        nav += '</a>';
      }
      nav += '</div>';
    }
    document.getElementById('s-nav').innerHTML = nav;

    // Content
    let html = '';
    for (const [ns, methods] of groups) {
      for (const m of methods) {
        html += renderMethod(m);
      }
    }
    document.getElementById('content').innerHTML = html;

    // Wire up try-it toggles
    document.querySelectorAll('.try-toggle').forEach(el => {
      el.addEventListener('click', () => {
        el.classList.toggle('open');
        el.nextElementSibling.classList.toggle('open');
      });
    });

    // Wire up send buttons
    document.querySelectorAll('.btn-send').forEach(el => {
      el.addEventListener('click', () => tryIt(el));
    });

    // Nav highlight on scroll
    const cards = document.querySelectorAll('.method-card');
    const observer = new IntersectionObserver(entries => {
      for (const e of entries) {
        if (e.isIntersecting) {
          document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
          const link = document.querySelector('.nav-item[href="#' + e.target.id + '"]');
          if (link) link.classList.add('active');
        }
      }
    }, { threshold: 0.3 });
    cards.forEach(c => observer.observe(c));
  }

  function renderMethod(m) {
    const parts = m.name.split('.');
    const ns = parts.slice(0, -1).join('.');
    const short = parts.pop();
    const nameHtml = ns ? '<span class="ns">' + esc(ns) + '.</span>' + esc(short) : esc(m.name);
    const streaming = m['x-streaming'] ? '<span class="badge badge-stream">streaming</span>' : '';
    const summary = m.summary ? '<div class="method-summary">' + esc(m.summary) + '</div>' : '';

    // Params table
    let paramsHtml = '';
    if (m.params.length) {
      paramsHtml = '<div class="section-title">Parameters</div><table class="params-table"><thead><tr>' +
        '<th>Name</th><th>Type</th><th>Required</th><th>Default</th></tr></thead><tbody>';
      for (const p of m.params) {
        const req = p.required
          ? '<span class="param-req yes">required</span>'
          : '<span class="param-req no">optional</span>';
        const def = p.schema.default !== undefined
          ? '<span class="param-default">' + esc(JSON.stringify(p.schema.default)) + '</span>'
          : '';
        paramsHtml += '<tr><td class="param-name">' + esc(p.name) + '</td>' +
          '<td class="param-type">' + esc(schemaType(p.schema)) + '</td>' +
          '<td>' + req + '</td><td>' + def + '</td></tr>';
      }
      paramsHtml += '</tbody></table>';
    } else {
      paramsHtml = '<div class="section-title">Parameters</div><div style="color:var(--text2);font-size:13px">None</div>';
    }

    // Return type
    const retType = schemaType(m.result?.schema);
    const retHtml = '<div class="section-title">Returns</div><span class="return-type">' + esc(retType) + '</span>';

    // Try It
    const example = JSON.stringify(buildExample(m), null, 2);
    const streamNote = m['x-streaming']
      ? '<div style="font-size:12px;color:var(--orange);margin-bottom:6px">This method returns an SSE stream. Only the initial response is shown here.</div>'
      : '';
    const tryHtml = '<div class="try-it">' +
      '<div class="try-toggle"><span class="arrow">&#9654;</span> Try It</div>' +
      '<div class="try-panel">' + streamNote +
      '<textarea class="try-json" spellcheck="false">' + esc(example) + '</textarea>' +
      '<div class="try-actions">' +
      '<button class="btn btn-primary btn-send" data-method="' + esc(m.name) + '">Send</button>' +
      '<button class="btn btn-secondary btn-reset" onclick="session&&session.reset();this.nextElementSibling.textContent=\'Session reset\'">Reset Session</button>' +
      '<span class="try-status"></span></div>' +
      '<div class="response-area"></div></div></div>';

    return '<div class="method-card" id="' + esc(m.name) + '">' +
      '<div class="method-header"><div class="method-name">' + nameHtml + streaming + '</div>' + summary + '</div>' +
      '<div class="method-body">' + paramsHtml + retHtml + tryHtml + '</div></div>';
  }

  async function tryIt(btn) {
    const card = btn.closest('.method-card');
    const textarea = card.querySelector('.try-json');
    const status = card.querySelector('.try-status');
    const respArea = card.querySelector('.response-area');

    let body;
    try {
      body = JSON.parse(textarea.value);
    } catch (e) {
      status.textContent = 'Invalid JSON';
      return;
    }

    status.textContent = 'Sending...';
    respArea.innerHTML = '';

    try {
      if (!session) session = new McpSession();
      const result = await session.call(body.method, body.params || {});
      const isErr = result?.error;
      const cls = isErr ? 'resp-err' : 'resp-ok';
      respArea.innerHTML = '<pre class="' + cls + '">' + esc(JSON.stringify(result, null, 2)) + '</pre>';
      status.textContent = isErr ? 'Error' : 'OK';
    } catch (e) {
      respArea.innerHTML = '<pre class="resp-err">' + esc(e.message) + '</pre>';
      status.textContent = 'Failed';
      session?.reset();
    }
  }

  function esc(s) {
    if (typeof s !== 'string') return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // -- Init --
  fetch('./openrpc.json')
    .then(r => r.json())
    .then(data => { spec = data; render(); })
    .catch(e => {
      document.getElementById('content').innerHTML =
        '<div class="empty"><h2>Failed to load spec</h2><p>' + esc(e.message) + '</p></div>';
    });
})();
</script>
</body>
</html>
"""
