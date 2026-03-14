"""Map event wire-protocol types — shared contract between BFF and BEs."""

from __future__ import annotations

from dataclasses import dataclass

from flights_backend.models.latlng import LatLng

NOTIFICATION_METHOD = "notifications/map.event"


@dataclass(slots=True)
class MapReadyEvent:
    """Map component is mounted and ready in the browser."""

    channel: str | None = None
    cid: str | None = None


MapBroadcastEvent = MapReadyEvent


def parse_map_event(params: dict) -> MapBroadcastEvent | None:
    """Parse a map event from notification params (subset used by flights BE).

    Returns None for event types this BE doesn't handle.
    """
    etype = params.get("type")
    channel = params.get("channel")
    cid = params.get("cid")
    match etype:
        case "map-ready":
            return MapReadyEvent(channel=channel, cid=cid)
        case _:
            raise ValueError(f"Unknown handled map event type: {etype}")
