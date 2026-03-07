from pyview_map.views.components.shared.fan_out_queue import FanOutQueue
from pyview_map.views.components.dynamic_map.models.map_events import MapCommand

command_queue: FanOutQueue[MapCommand] = FanOutQueue()
