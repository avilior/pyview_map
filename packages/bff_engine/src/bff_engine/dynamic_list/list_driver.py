from pyview.events import InfoEvent
from pyview.template.live_view_template import live_component

from .sources.api_list_source import list_store
from .dynamic_list import DynamicListComponent, ItemRenderer, default_item_renderer
from bff_engine.shared.event_broadcaster import EventBroadcaster
from bff_engine.shared.cid import next_cid
from bff_engine.shared.topics import list_ops_topic, list_cmd_topic
from dmap_models.list_events import ListItemClickEvent, ListReadyEvent


class ListDriver:
    """Encapsulates all parent-side plumbing for hosting a DynamicListComponent.

    Each driver instance gets a unique cid (channel instance ID) via a
    monotonic counter, shared across all its subscriptions.

    Data arrives reactively via PubSub — no tick polling needed.

    Usage::

        class MyPageView(TemplateView, LiveView[MyContext]):
            async def mount(self, socket, session):
                self._list = ListDriver("my-list")
                socket.context = MyContext()
                if socket.connected:
                    await self._list.connect(socket)

            async def handle_info(self, event, socket):
                await self._list.handle_info(event, socket)

            async def handle_event(self, event, payload, socket):
                self._list.clear_ops()
                summary = self._list.handle_event(event, payload)
                if summary:
                    socket.context.last_event = summary

            def template(self, assigns, meta):
                return t'<div>{self._list.render()}</div>'
    """

    def __init__(self, channel: str, item_renderer: ItemRenderer = default_item_renderer):
        self._channel = channel
        self._item_renderer = item_renderer
        self._cid = next_cid()
        self._initial_items = list_store.all_items(channel)
        self._list_ops: list[dict] = []
        self._ops_version: int = 0

        # Pre-compute PubSub topic sets for handle_info matching
        ch = channel
        cid = self._cid
        self._ops_topics = {list_ops_topic(ch), list_ops_topic(ch, cid)}
        self._cmd_topics = {list_cmd_topic(ch), list_cmd_topic(ch, cid)}

    @property
    def cid(self) -> str:
        """The channel instance ID for this driver."""
        return self._cid

    async def connect(self, socket):
        """Subscribe to PubSub topics. Call when socket.connected."""
        for topic in self._ops_topics:
            await socket.subscribe(topic)
        for topic in self._cmd_topics:
            await socket.subscribe(topic)

    def disconnect(self):
        """Clear retained events for this driver's channel."""
        EventBroadcaster.clear_retained(f"list-ready:{self._channel}")

    async def handle_info(self, event: InfoEvent, socket) -> bool:
        """Process PubSub messages. Returns True if handled.

        Call from the parent LiveView's handle_info for each driver.
        """
        topic = event.name

        # Reset ops from previous render cycle
        self._list_ops = []

        if topic in self._ops_topics:
            self._list_ops = [event.payload]
            self._ops_version += 1
            return True

        if topic in self._cmd_topics:
            cmd = event.payload
            event_name, payload = cmd.to_push_event(target=self._channel)
            await socket.push_event(event_name, payload)
            return True

        return False

    def clear_ops(self):
        """Clear stale ops so component doesn't re-apply. Call at start of handle_event."""
        self._list_ops = []

    def handle_event(self, event: str, payload: dict) -> str | None:
        """Parse item-click events, broadcast, return summary or None."""
        if event == "item-click":
            item_id = payload.get("id", "")
            label = payload.get("label", "")
            evt = ListItemClickEvent(event="click", id=item_id, label=label, channel=self._channel, cid=self._cid)
            EventBroadcaster.broadcast(evt)
            return f"click → {label}"
        elif event == "list-ready":
            EventBroadcaster.broadcast(ListReadyEvent(channel=self._channel, cid=self._cid))
            return "list ready"
        return None

    def render(self):
        """Return live_component() call with current state."""
        return live_component(
            DynamicListComponent,
            id=self._channel,
            initial_items=self._initial_items,
            list_ops=self._list_ops,
            ops_version=self._ops_version,
            channel=self._channel,
            item_renderer=self._item_renderer,
        )
