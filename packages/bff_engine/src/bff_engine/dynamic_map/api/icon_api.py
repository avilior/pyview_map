from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from pyview.live_socket import pub_sub_hub

from bff_engine.dynamic_map.icon_registry import icon_registry
from bff_engine.dynamic_map.models.icon_commands import UpdateIconRegistryCmd
from bff_engine.shared.topics import icon_cmd_topic


async def _broadcast_registry() -> None:
    """Push the full icon registry to all connected MapDrivers."""
    cmd = UpdateIconRegistryCmd(registry_json=icon_registry.to_json())
    await pub_sub_hub.send_all_on_topic_async(icon_cmd_topic(), cmd)


@jrpc_service.request("icons.add")
async def icons_add(
    name: str,
    html: str,
    iconSize: list[int],
    iconAnchor: list[int],
    className: str = "",
) -> dict:
    definition = {
        "html": html,
        "iconSize": iconSize,
        "iconAnchor": iconAnchor,
        "className": className,
    }
    icon_registry.register(name, definition)
    await _broadcast_registry()
    return {"ok": True}


@jrpc_service.request("icons.remove")
async def icons_remove(name: str) -> dict:
    removed = icon_registry.remove(name)
    if removed:
        await _broadcast_registry()
    return {"ok": removed}


@jrpc_service.request("icons.list")
def icons_list() -> dict:
    return {"icons": icon_registry.icons}
