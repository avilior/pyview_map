import asyncio

from http_stream_client.jsonrpc.client_sdk import (
    ClientRPC,
    JSONRPCErrorResponse,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from parks import national_parks

from pyview_map.views.components.dynamic_list import DListItem
from pyview_map.views.components.dynamic_list.models.list_events import ListItemClickEvent, ListItemOpEvent
from pyview_map.views.components.dynamic_map.models.dmarker import DMarker
from pyview_map.views.components.dynamic_map.models.map_events import parse_event


# Parks Service is the source of truth for national parks.
# It uses a GUI that live at the BASE URL to display the list of national parks.
# TODO: Is park service a client or a server or both.  Currently it acts like a client since it initiates a connection to the GUI Service to display the parks.

BASE_URL = "http://localhost:8123/api"  # GUI service.
AUTH_TOKEN = "tok-acme-001"

async def event_listener(rpc: ClientRPC):

    def find_park(park_id: str):
        np = national_parks.get(park_id, None)
        if np is None:
            print(f"park not found: {park_id}")
            return None
        return np

    req = JSONRPCRequest(method="map.events.subscribe")

    async for msg in rpc.send_request(req):
        match msg:
            case JSONRPCNotification() if isinstance(msg.params, dict):
                evt = parse_event(msg.params)
                print(f"[RX {msg.method}] channel: {evt.channel} cid: {evt.cid} >",end="")
                match evt:
                    case ListItemClickEvent():
                        # when clicking on a list item, i want the map to flyto the selected park.
                        print(f"  [list-click] {evt.id} label={evt.label}")
                        if (np := find_park(evt.id)) is None:
                            print(f"park not found: {evt.id}")
                            continue

                        target_map_channel = "places-map"
                        target_map_cid = "*"  # send to all maps on the channel
                        params = {"channel": target_map_channel, "cid": target_map_cid, "latLng": np.lat_lng.to_list(), "zoom": 12}
                        print(f"Sending event to map: {params}")
                        async for resp in rpc.send_request(JSONRPCRequest(method="map.setView", params=params)):
                            print(F"JSONRPC resp: {resp}")

                    case ListItemOpEvent():
                        match evt.op:
                            case "add":
                                print(f"    [list-add] {evt.id} label={evt.label}")
                                # use the evt.id to lookup the park in the national parks dictionary

                                if (np := find_park(evt.id)) is None:
                                    continue

                                # TODO send add op to all the maps to display the new park.
                                target_map_channel = "places-map"
                                target_map_cid = "*"  # send to all maps on the channel
                                # create the marker for the park
                                try:
                                    park_marker = DMarker(id=np.name, name=np.name, lat_lng=np.lat_lng, icon=np.icon)
                                    params = park_marker.to_dict()
                                    params["channel"] = target_map_channel
                                    print(f"adding marker to map: {params}")
                                    async for resp in rpc.send_request(JSONRPCRequest(method="markers.add", params=params)):
                                        print(resp)
                                except Exception as e:
                                    print(f"Error adding marker to map: {e}")

                            case "delete":
                                print(f"    [list-delete] {evt.id} label={evt.label}")
                            case _:
                                print(f"    [list-op] unhandled op={evt.op}")
                    case _:
                        print(f"  [event] {evt}")

            case JSONRPCResponse():
                print(f"Response received: {msg} END OF CHANNEL")
            case JSONRPCErrorResponse():
                print(f"Error response received: {msg}")
            case _:
                print(f"Unknown message type: {type(msg)}")


async def main():

    print("Parks Service starting up... attempting to connect to GUI Service")

    all_tasks = []

    async with ClientRPC(base_url=BASE_URL, auth_token=AUTH_TOKEN) as rpc:
        print(F"Connected: {BASE_URL}")
        print("Register for events....")

        all_tasks.append(asyncio.create_task(event_listener(rpc)))

        print("Listening for events... (Ctrl+C to stop)")

        print("Populate the list")
        for np in national_parks.values():
            # The api for adding items to the list can be found at pyview_map.views.componetns.dynamic_list.api_list_api
            #     id: str,  JSONRPC id dont care about that
            #     label: str, the name of the park
            #     channel: str,  the component channel or name
            #     subtitle: str = "", subtitile
            #     at: int = -1,       index to insert at
            #     cid: str = "*",     the component instance id a '*' means braodcast to all instances on the channel

            # A list item is modeled using a DListItem class which is defined in pyview_map.views.components.dynamic_list.models.dlist_item
            list_item = DListItem(id=np.name, label=np.name, subtitle=np.description, data={"icon": np.icon})
            list_channel = "places-list" # found by looking at the places_demo file.  The base name of the application and the list component name

            params = {"id": list_item.id,
                      "label": list_item.label,
                      "subtitle": list_item.subtitle,
                      "data": list_item.data,
                      "channel": list_channel}

            add_request = JSONRPCRequest(method="list.add", params=params)
            async for resp in rpc.send_request(request=add_request):
                print(resp)

        try:
            while True:
                await asyncio.sleep(1)

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("Stopping...")
            for task in all_tasks:
                task.cancel()
            await asyncio.gather(*all_tasks, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())