from fastapi import FastAPI, Request

from pyview_map.views.dynamic_map.api_marker_source import APIMarkerSource

api_app = FastAPI(title="dmap Marker API")


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


@api_app.post("/rpc")
async def rpc_endpoint(request: Request):
    body = await request.json()
    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if method == "markers.add":
        APIMarkerSource.push_add(params["id"], params["name"], params["latLng"])
        return _ok(req_id, {"ok": True})
    elif method == "markers.update":
        APIMarkerSource.push_update(params["id"], params["name"], params["latLng"])
        return _ok(req_id, {"ok": True})
    elif method == "markers.delete":
        APIMarkerSource.push_delete(params["id"])
        return _ok(req_id, {"ok": True})
    elif method == "markers.list":
        return _ok(req_id, {"markers": [m.to_dict() for m in APIMarkerSource._markers.values()]})
    else:
        return _error(req_id, -32601, f"Method not found: {method}")
