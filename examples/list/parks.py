from dataclasses import dataclass
from pyview_map.views.components.shared.latlng import LatLng


@dataclass
class NationalPark:
    name: str
    lat_lng: LatLng
    description: str
    icon: str


national_parks: dict[str, NationalPark] = {
    "Yellowstone National Park": NationalPark(
        name="Yellowstone National Park",
        lat_lng=LatLng(44.4280, -110.5885),
        description="America's first national park, known for its geothermal features like Old Faithful.",
        icon="🌋",
    ),
    "Yosemite National Park": NationalPark(
        name="Yosemite National Park",
        lat_lng=LatLng(37.8651, -119.5383),
        description="Famous for its giant, ancient sequoias, and the towering Bridalveil Fall.",
        icon="🌲",
    ),
    "Grand Canyon National Park": NationalPark(
        name="Grand Canyon National Park",
        lat_lng=LatLng(36.1069, -112.1129),
        description="Iconic national park featuring a massive canyon carved by the Colorado River.",
        icon="🏜️",
    ),
    "Saguaro National Park": NationalPark(
        name="Saguaro National Park",
        lat_lng=LatLng(32.2967, -111.1667),
        description="Named for the giant saguaro cactus, it offers desert landscapes and diverse wildlife.",
        icon="🌵",
    ),
    "Zion National Park": NationalPark(
        name="Zion National Park",
        lat_lng=LatLng(37.2982, -113.0263),
        description="Known for Zion Canyon's steep red cliffs and scenic hiking trails.",
        icon="🏞️",
    ),
    "Rocky Mountain National Park": NationalPark(
        name="Rocky Mountain National Park",
        lat_lng=LatLng(40.3428, -105.6836),
        description="Home to spectacular mountain environments, including Longs Peak and Trail Ridge Road.",
        icon="🏔️",
    ),
    "Glacier National Park": NationalPark(
        name="Glacier National Park",
        lat_lng=LatLng(48.7596, -113.7870),
        description="Features rugged mountains, pristine forests, and alpine meadows.",
        icon="❄️",
    ),
    "Great Smoky Mountains National Park": NationalPark(
        name="Great Smoky Mountains National Park",
        lat_lng=LatLng(35.6118, -83.4895),
        description="Renowned for its biodiversity, misty mountains, and lush forests.",
        icon="🌫️",
    ),
    "Grand Teton National Park": NationalPark(
        name="Grand Teton National Park",
        lat_lng=LatLng(43.7904, -110.6818),
        description="Famous for its stunning mountain scenery and diverse wildlife.",
        icon="🏔️",
    ),
    "Olympic National Park": NationalPark(
        name="Olympic National Park",
        lat_lng=LatLng(47.8021, -123.6044),
        description="Diverse ecosystems ranging from Pacific coastline to alpine peaks.",
        icon="🏞️",
    ),
    "Acadia National Park": NationalPark(
        name="Acadia National Park",
        lat_lng=LatLng(44.3386, -68.2733),
        description="Known for its rocky beaches, woodland, and the tallest mountain on the U.S. East Coast.",
        icon="🏞️",
    ),
    "Joshua Tree National Park": NationalPark(
        name="Joshua Tree National Park",
        lat_lng=LatLng(33.8734, -115.9010),
        description="Unique desert landscapes with Joshua trees and rugged rock formations.",
        icon="🌵",
    ),
    "Arches National Park": NationalPark(
        name="Arches National Park",
        lat_lng=LatLng(38.7331, -109.5925),
        description="Home to more than 2,000 natural stone arches and stunning red rock formations.",
        icon="🪨",
    ),
    "Bryce Canyon National Park": NationalPark(
        name="Bryce Canyon National Park",
        lat_lng=LatLng(37.5930, -112.1871),
        description="Known for its unique geologic formations called hoodoos.",
        icon="🏞️",
    ),
    "Shenandoah National Park": NationalPark(
        name="Shenandoah National Park",
        lat_lng=LatLng(38.2928, -78.6796),
        description="Features the scenic Skyline Drive and part of the Appalachian Trail.",
        icon="🌄",
    ),
    "Everglades National Park": NationalPark(
        name="Everglades National Park",
        lat_lng=LatLng(25.2866, -80.8987),
        description="Largest subtropical wilderness in the U.S., famous for its wildlife and sawgrass marshes.",
        icon="🌿",
    ),
}