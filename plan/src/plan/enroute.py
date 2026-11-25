"""Weather along a plan's route: winds aloft and hazards reported nearby."""

from dataclasses import dataclass
import math
from types import SimpleNamespace

from .generate import GRADIENT, course, nm
from .grib import WindsAloft
from .weather import Challenge, challenge

# Spacing of the points the route is sampled at, nm
STEP_NM = 20
# METARs this close to the route count as enroute weather, nm
NEAR_ROUTE_NM = 25
# The strongest wind is reported from here up, where it affects the cruise
STRONGEST_FROM_FT = 10000
# Hazards that matter in cruise, not just on the runway
ENROUTE_HAZARDS = ("⛈", "❄", "💨")
# The aircraft counts as on the route within this distance of it, nm
ON_ROUTE_NM = 50


def path_waypoints(plan):
    """The path drawn on the map: SID, enroute, STAR and approach.

    Procedure fixes carry no altitude, so they get the climb and descent
    profile between the planned cruise and the airports.
    """
    path = []
    for _, waypoints in plan.segments:
        for w in waypoints:
            if not path or path[-1].name != w.name:
                path.append(w)
    if len(path) < 2:
        path = list(plan.waypoints)
    planned = {w.name: w.altitude for w in plan.waypoints if w.altitude is not None}
    cruise = max(planned.values(), default=0)
    dep_elev = plan.waypoints[0].altitude or 0 if plan.waypoints else 0
    des_elev = plan.waypoints[-1].altitude or 0 if plan.waypoints else 0
    along = [0.0]
    for a, b in zip(path, path[1:]):
        along.append(along[-1] + nm((a.latitude, a.longitude), (b.latitude, b.longitude)))
    total = along[-1]
    return [
        SimpleNamespace(
            name=w.name,
            latitude=w.latitude,
            longitude=w.longitude,
            altitude=planned.get(w.name)
            if w.name in planned
            else min(cruise, dep_elev + d * GRADIENT, des_elev + (total - d) * GRADIENT),
        )
        for w, d in zip(path, along)
    ]


def route_length(waypoints) -> float:
    return sum(
        nm((a.latitude, a.longitude), (b.latitude, b.longitude))
        for a, b in zip(waypoints, waypoints[1:])
    )


def position_along(points, lat, lon) -> float | None:
    """Distance from departure of the route point nearest the aircraft, None
    when the aircraft is not near the route"""
    if not points or lat is None or lon is None:
        return None
    nearest = min(points, key=lambda p: nm((p.lat, p.lon), (lat, lon)))
    if nm((nearest.lat, nearest.lon), (lat, lon)) > ON_ROUTE_NM:
        return None
    return nearest.along


@dataclass
class RoutePoint:
    lat: float
    lon: float
    altitude: float
    track: float
    # Distance from departure, nm
    along: float


def route_points(waypoints, step=STEP_NM) -> list[RoutePoint]:
    """Points every step nm along the waypoints, altitude interpolated."""
    points = []
    along = 0.0
    for a, b in zip(waypoints, waypoints[1:]):
        pa, pb = (a.latitude, a.longitude), (b.latitude, b.longitude)
        leg = nm(pa, pb)
        if leg == 0:
            continue
        track = course(pa, pb)
        alt_a = a.altitude or 0
        alt_b = b.altitude or 0
        count = max(1, math.ceil(leg / step))
        for k in range(count):
            f = k / count
            points.append(
                RoutePoint(
                    lat=pa[0] + (pb[0] - pa[0]) * f,
                    lon=pa[1] + (pb[1] - pa[1]) * f,
                    altitude=alt_a + (alt_b - alt_a) * f,
                    track=track,
                    along=along + leg * f,
                )
            )
        along += leg
    return points


@dataclass
class EnrouteWind:
    # Average along track component, kt; positive is a tailwind
    component: float
    # Strongest wind above STRONGEST_FROM_FT, or anywhere on a low route:
    # direction, speed kt and distance from departure nm
    max_direction: float
    max_speed: float
    max_along: float


def enroute_wind(points: list[RoutePoint], winds: WindsAloft) -> EnrouteWind | None:
    if not points:
        return None
    components = []
    strongest = (0.0, 0.0, 0.0)
    strongest_low = (0.0, 0.0, 0.0)
    for p in points:
        direction, speed = winds.wind(p.lat, p.lon, p.altitude)
        # The wind blows towards direction + 180
        components.append(speed * math.cos(math.radians(direction + 180 - p.track)))
        if p.altitude >= STRONGEST_FROM_FT:
            if speed > strongest[1]:
                strongest = (direction, speed, p.along)
        elif speed > strongest_low[1]:
            strongest_low = (direction, speed, p.along)
    cruised = any(p.altitude >= STRONGEST_FROM_FT for p in points)
    return EnrouteWind(
        sum(components) / len(components), *(strongest if cruised else strongest_low)
    )


@dataclass
class EnrouteHazard:
    station: str
    challenge: Challenge
    # Distance from departure of the nearest route point, nm
    along: float


def enroute_hazard(points, stations, metar) -> EnrouteHazard | None:
    """Worst cruise hazard in METARs from stations near the route.

    stations maps ICAO to (lat, lon); metar(icao) gives the parsed METAR.
    """
    hazards = enroute_hazards(points, stations, metar)
    return max(hazards, key=lambda h: h.challenge.score, default=None)


def enroute_hazards(points, stations, metar) -> list[EnrouteHazard]:
    """Every cruise hazard in METARs from stations near the route, in route order"""
    if not points:
        return []
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    margin = NEAR_ROUTE_NM / 60
    found = []
    for icao, (lat, lon) in stations.items():
        # Cheap box test before measuring distances
        if not (min(lats) - margin <= lat <= max(lats) + margin):
            continue
        lon_margin = margin / max(math.cos(math.radians(lat)), 0.2)
        if not (min(lons) - lon_margin <= lon <= max(lons) + lon_margin):
            continue
        nearest = min(points, key=lambda p: nm((p.lat, p.lon), (lat, lon)))
        if nm((nearest.lat, nearest.lon), (lat, lon)) > NEAR_ROUTE_NM:
            continue
        wx = challenge(metar(icao), [])
        if wx.icon not in ENROUTE_HAZARDS:
            continue
        found.append(EnrouteHazard(icao, wx, nearest.along))
    return sorted(found, key=lambda h: h.along)


def enroute_text(wind: EnrouteWind | None, hazard: EnrouteHazard | None) -> str:
    """e.g. "head 35kt, max 260/99 at 140nm · ⛈ TS LFPG at 210nm" """
    parts = []
    if wind:
        kind = "tail" if wind.component >= 0 else "head"
        parts.append(
            f"{kind} {abs(wind.component):.0f}kt, max "
            f"{wind.max_direction:03.0f}/{wind.max_speed:.0f} at {wind.max_along:.0f}nm"
        )
    if hazard:
        parts.append(
            f"{hazard.challenge.icon} {hazard.challenge.notes} {hazard.station} "
            f"at {hazard.along:.0f}nm"
        )
    return " · ".join(parts)
