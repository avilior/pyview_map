import math
from datetime import datetime, timedelta
from typing import Iterator, Tuple
from pyview_map.views.components.dynamic_map.latlng import LatLng

EARTH_RADIUS_NM = 3440.065  # nautical miles


def latlng_degree_to_rad(latlng_degrees: LatLng):
    return LatLng(lat=math.radians(latlng_degrees.lat), lng=math.radians(latlng_degrees.lng))

def _great_circle_fraction_point(
    from_latlng: LatLng,
    to_latlng: LatLng,
    f: float
) -> LatLng:
    """
    Point at fraction f along great-circle from (lat1,lon1) to (lat2,lon2).
    f=0 -> start, f=1 -> end.
    """

    from_latlng_rad = latlng_degree_to_rad(from_latlng)
    to_latlng_rad = latlng_degree_to_rad(to_latlng)
    lat1, lon1 = from_latlng_rad.lat, from_latlng_rad.lng
    lat2, lon2 = to_latlng_rad.lat, to_latlng_rad.lng

    # Angular distance between points
    delta_sigma = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))

    if delta_sigma == 0:
        return LatLng(from_latlng.lat, from_latlng.lng)

    # Slerp on the unit sphere
    A = math.sin((1 - f) * delta_sigma) / math.sin(delta_sigma)
    B = math.sin(f * delta_sigma) / math.sin(delta_sigma)

    x = A * math.cos(lat1) * math.cos(lon1) + B * math.cos(lat2) * math.cos(lon2)
    y = A * math.cos(lat1) * math.sin(lon1) + B * math.cos(lat2) * math.sin(lon2)
    z = A * math.sin(lat1) + B * math.sin(lat2)

    lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
    lon = math.degrees(math.atan2(y, x))
    lon = (lon + 540) % 360 - 180  # normalize to [-180,180)

    return LatLng(lat, lon)


def great_circle_position_at_time(
    from_latlng: LatLng,
    to_latlng: LatLng,
    ground_speed_knots: float,
    start_time: datetime,
    current_time: datetime
) -> LatLng:
    """
    Return aircraft position at current_time along great-circle between two points.

    If current_time <= start_time -> start point.
    If current_time >= arrival_time -> end point.
    Otherwise interpolate according to elapsed fraction.
    """
    # Compute total distance and arrival time
    from_latlng_rad = latlng_degree_to_rad(from_latlng)
    to_latlng_rad = latlng_degree_to_rad(to_latlng)
    lat1, lon1 = from_latlng_rad.lat, from_latlng_rad.lng
    lat2, lon2 = to_latlng_rad.lat, to_latlng_rad.lng

    delta_sigma = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))

    total_distance_nm = EARTH_RADIUS_NM * delta_sigma
    total_hours = total_distance_nm / ground_speed_knots
    total_seconds = total_hours * 3600.0
    arrival_time = start_time + timedelta(seconds=total_seconds)

    if current_time <= start_time:
        return from_latlng
    if current_time >= arrival_time:
        return to_latlng

    elapsed = (current_time - start_time).total_seconds()
    f = elapsed / total_seconds  # fraction of trip completed

    return _great_circle_fraction_point(from_latlng, to_latlng, f)


def great_circle_flight_generator(
    from_latlng: LatLng,
    to_latlng: LatLng,
    ground_speed_knots: float,
    start_time: datetime,
    step: timedelta = timedelta(minutes=1)
) -> Iterator[Tuple[datetime, LatLng]]:
    """
    Generator yielding (timestamp, lat, lon) along great-circle route
    every 'step' from start_time until arrival.
    """
    # Precompute total duration
    from_latlng_rad = latlng_degree_to_rad(from_latlng)
    to_latlng_rad = latlng_degree_to_rad(to_latlng)
    lat1, lon1 = from_latlng_rad.lat, from_latlng_rad.lng
    lat2, lon2 = to_latlng_rad.lat, to_latlng_rad.lng

    delta_sigma = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))

    total_distance_nm = EARTH_RADIUS_NM * delta_sigma
    total_hours = total_distance_nm / ground_speed_knots
    total_seconds = total_hours * 3600.0
    arrival_time = start_time + timedelta(seconds=total_seconds)

    t = start_time
    while t < arrival_time:
        elapsed = (t - start_time).total_seconds()
        f = elapsed / total_seconds if total_seconds > 0 else 0.0
        latlng = _great_circle_fraction_point(from_latlng, to_latlng, f)
        yield t, latlng
        t += step

    # Final position exactly at arrival_time
    yield arrival_time, to_latlng


def bearing_deg(from_latlng: LatLng, to_latlng: LatLng) -> float:
    """
    Heading from (lat1, lon1) to (lat2, lon2) along the great-circle, in degrees.
    0° = north, 90° = east, 180° = south, 270° = west.
    """

    lat1 = math.radians(from_latlng.lat)
    lat2 = math.radians(to_latlng.lat)
    dlon = math.radians(to_latlng.lng - from_latlng.lng)

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)

    brng = math.degrees(math.atan2(y, x))
    # Normalize to [0, 360)
    return (brng + 360.0) % 360.0