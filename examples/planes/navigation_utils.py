import math
from datetime import datetime, timedelta
from typing import Iterator, Tuple

EARTH_RADIUS_NM = 3440.065  # nautical miles


def _great_circle_fraction_point(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
    f: float
) -> Tuple[float, float]:
    """
    Point at fraction f along great-circle from (lat1,lon1) to (lat2,lon2).
    f=0 -> start, f=1 -> end.
    """

    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)

    # Angular distance between points
    delta_sigma = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))

    if delta_sigma == 0:
        return lat1_deg, lon1_deg

    # Slerp on the unit sphere
    A = math.sin((1 - f) * delta_sigma) / math.sin(delta_sigma)
    B = math.sin(f * delta_sigma) / math.sin(delta_sigma)

    x = A * math.cos(lat1) * math.cos(lon1) + B * math.cos(lat2) * math.cos(lon2)
    y = A * math.cos(lat1) * math.sin(lon1) + B * math.cos(lat2) * math.sin(lon2)
    z = A * math.sin(lat1) + B * math.sin(lat2)

    lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
    lon = math.degrees(math.atan2(y, x))
    lon = (lon + 540) % 360 - 180  # normalize to [-180,180)

    return lat, lon


def great_circle_position_at_time(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
    ground_speed_knots: float,
    start_time: datetime,
    current_time: datetime
) -> Tuple[float, float]:
    """
    Return aircraft position at current_time along great-circle between two points.

    If current_time <= start_time -> start point.
    If current_time >= arrival_time -> end point.
    Otherwise interpolate according to elapsed fraction.
    """
    # Compute total distance and arrival time
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)

    delta_sigma = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))

    total_distance_nm = EARTH_RADIUS_NM * delta_sigma
    total_hours = total_distance_nm / ground_speed_knots
    total_seconds = total_hours * 3600.0
    arrival_time = start_time + timedelta(seconds=total_seconds)

    if current_time <= start_time:
        return lat1_deg, lon1_deg
    if current_time >= arrival_time:
        return lat2_deg, lon2_deg

    elapsed = (current_time - start_time).total_seconds()
    f = elapsed / total_seconds  # fraction of trip completed

    return _great_circle_fraction_point(lat1_deg, lon1_deg, lat2_deg, lon2_deg, f)


def great_circle_flight_generator(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
    ground_speed_knots: float,
    start_time: datetime,
    step: timedelta = timedelta(minutes=1)
) -> Iterator[Tuple[datetime, float, float]]:
    """
    Generator yielding (timestamp, lat, lon) along great-circle route
    every 'step' from start_time until arrival.
    """
    # Precompute total duration
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)

    delta_sigma = math.acos(math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))

    total_distance_nm = EARTH_RADIUS_NM * delta_sigma
    total_hours = total_distance_nm / ground_speed_knots
    total_seconds = total_hours * 3600.0
    arrival_time = start_time + timedelta(seconds=total_seconds)

    t = start_time
    while t < arrival_time:
        elapsed = (t - start_time).total_seconds()
        f = elapsed / total_seconds if total_seconds > 0 else 0.0
        lat, lon = _great_circle_fraction_point(lat1_deg, lon1_deg, lat2_deg, lon2_deg, f)
        yield t, lat, lon
        t += step

    # Final position exactly at arrival_time
    yield arrival_time, lat2_deg, lon2_deg


def bearing_deg(lat1_deg: float, lon1_deg: float,
                lat2_deg: float, lon2_deg: float) -> float:
    """
    Heading from (lat1, lon1) to (lat2, lon2) along the great-circle, in degrees.
    0° = north, 90° = east, 180° = south, 270° = west.
    """

    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)
    dlon = math.radians(lon2_deg - lon1_deg)

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)

    brng = math.degrees(math.atan2(y, x))
    # Normalize to [0, 360)
    return (brng + 360.0) % 360.0