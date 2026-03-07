from pyview_map.views.components.shared.fan_out_queue import FanOutQueue
from pyview_map.views.components.dynamic_list.models.list_events import ListCommand

list_command_queue: FanOutQueue[ListCommand] = FanOutQueue()
