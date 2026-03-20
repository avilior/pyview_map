"""PubSub topic naming for component data and command channels.

Convention: ``{prefix}:{channel}`` for broadcast (cid="*"),
``{prefix}:{channel}:{cid}`` for targeted delivery.
"""


def _topic(prefix: str, channel: str, cid: str = "*") -> str:
    return f"{prefix}:{channel}" if cid == "*" else f"{prefix}:{channel}:{cid}"


def marker_ops_topic(channel: str, cid: str = "*") -> str:
    return _topic("marker-ops", channel, cid)


def polyline_ops_topic(channel: str, cid: str = "*") -> str:
    return _topic("polyline-ops", channel, cid)


def map_cmd_topic(channel: str, cid: str = "*") -> str:
    return _topic("map-cmd", channel, cid)


def list_ops_topic(channel: str, cid: str = "*") -> str:
    return _topic("list-ops", channel, cid)


def list_cmd_topic(channel: str, cid: str = "*") -> str:
    return _topic("list-cmd", channel, cid)


def icon_cmd_topic() -> str:
    """Global topic for icon registry updates (not per-channel)."""
    return "icon-cmd"
