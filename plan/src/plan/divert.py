"""Diversions: airports near the aircraft, their runways, and manual vectors
onto the final approach of the chosen runway."""

from dataclasses import dataclass
import math

from .apt import heading_and_length
from .generate import Generator, course, nm

# Final approach length, nm: the intercept point is this far from the threshold
FINAL_NM = 10
# Angle between the intercept heading and the final approach course
INTERCEPT_ANGLE = 30
# Length of the intercept leg before it meets the final approach, nm
INTERCEPT_NM = 4
# Threshold crossing height, ft
THRESHOLD_HEIGHT = 50
# A localizer further than this off the runway heading is offset, and the
# vectors then follow the runway
ALIGNED_DEGREES = 3
# Expedited descent rate with speed brakes, ft/min
EXPEDITE_FPM = 3000
# A normal descent, about 3 degrees, ft per nm
DESCENT_FT_PER_NM = 318
# Ground speed assumed when the sim gives none, kt
DEFAULT_SPEED_KT = 250
# Level deceleration, nm per kt lost: about 1nm per 10kt
DECEL_NM_PER_KT = 0.1
# Speed at the end of the intercept leg, about F speed with CONF 2
INTERCEPT_END_KT = 180
# Height above the threshold to be stable at Vapp, ft
STABLE_FT = 1000
# Vapp wind correction: a third of the headwind, within these limits, kt
APPR_COR_MIN = 5
APPR_COR_MAX = 15
# Airports listed as nearby, and how far to look, nm
NEARBY_COUNT = 30
NEARBY_RADIUS = 400
M_TO_FT = 3.28084


@dataclass
class Ils:
    ident: str
    frequency: float
    course_mag: float
    course_true: float
    glideslope: float | None
    category: str


@dataclass
class RunwayEnd:
    name: str
    lat: float
    lon: float
    length_ft: int
    heading_true: float
    elevation_ft: int
    ils: Ils | None

    @property
    def aligned_ils(self):
        """The localizer when it runs along the runway, None when offset"""
        if not self.ils:
            return None
        off = abs((self.ils.course_true - self.heading_true + 180) % 360 - 180)
        return self.ils if off <= ALIGNED_DEGREES else None

    @property
    def final_true(self):
        return self.aligned_ils.course_true if self.aligned_ils else self.heading_true

    def heading_mag(self, variation):
        """Magnetic final course; an aligned localizer's own course"""
        if self.aligned_ils:
            return self.aligned_ils.course_mag
        return (self.heading_true + variation) % 360


@dataclass
class Nearby:
    icao: str
    iata: str
    city: str
    name: str
    distance: float
    bearing_true: float
    elevation_ft: int
    # Extra track needed to get down in time, nm; 0 when there is enough
    too_high_nm: float


@dataclass
class Leg:
    label: str
    heading_mag: float
    distance: float
    # Speed at the end of the leg, kt
    speed_kt: float = 0
    minutes: float = 0


@dataclass
class Speeds:
    """Approach speeds for the landing weight and runway wind"""

    weight_kg: float
    conf: str
    vls: float
    vapp: float
    green_dot: float
    # Headwind on the runway, kt, negative for a tailwind
    headwind: float


def green_dot(weight_kg) -> float:
    """Rule of thumb green dot below FL200: twice the weight in tonnes + 85"""
    return 2 * weight_kg / 1000 + 85


def headwind(wind, heading_true) -> float:
    """Headwind component, kt, of a METAR (direction or None, speed) wind"""
    if not wind or wind[0] is None:
        return 0.0
    direction, speed = wind
    return speed * math.cos(math.radians(direction - heading_true))


def speeds(airframe, weight_kg, wind, runway: "RunwayEnd", conf="FULL") -> Speeds:
    """VLS, Vapp (VLS plus a third of the headwind) and green dot"""
    vls = airframe.vls(conf, weight_kg)
    head = headwind(wind, runway.heading_true)
    correction = min(max(head / 3, APPR_COR_MIN), APPR_COR_MAX)
    return Speeds(
        weight_kg=weight_kg,
        conf=conf,
        vls=vls,
        vapp=vls + correction,
        green_dot=green_dot(weight_kg),
        headwind=head,
    )


def expedite_ft_per_nm(ground_speed_kt) -> float:
    """Expedited descent gradient at a ground speed"""
    return EXPEDITE_FPM * 60 / (ground_speed_kt or DEFAULT_SPEED_KT)


def minutes(distance, start_kt, end_kt) -> float:
    """Time to fly distance nm while slowing evenly from start_kt to end_kt"""
    average = max((start_kt + end_kt) / 2, 50)
    return distance / average * 60


@dataclass
class Vectors:
    legs: list[Leg]
    # Altitude to be at on joining final, for its glide path
    intercept_alt_ft: int
    glide_angle: float
    total_nm: float
    eta_min: float | None
    # Aircraft, join point, intercept point and threshold, for the map
    points: list[tuple[float, float]]
    # When to leave the current altitude to be at intercept_alt_ft at the
    # start of the deceleration, e.g. "start descent in 22nm", "descend now",
    # "too high, +15nm"
    descent: str = ""
    speeds: Speeds | None = None
    # Level deceleration to green dot at the end of the direct leg, nm
    decel_nm: float = 0


def read_ils(earth_nav_path) -> dict:
    """ICAO -> runway -> Ils, from the localizer and glideslope rows.

    A localizer's bearing field holds magnetic course x 360 plus the true
    course, a glideslope's holds the angle x 100000 plus the true course.
    """
    localizers, glideslopes = {}, {}
    with open(earth_nav_path) as f:
        for line in f:
            p = line.split()
            if len(p) < 11 or p[0] not in ("4", "6"):
                continue
            key = (p[8], p[10])
            value = float(p[6])
            if p[0] == "4":
                magnetic = int(value // 360)
                category = p[11].removeprefix("ILS-cat-") if len(p) > 11 else ""
                localizers[key] = Ils(
                    ident=p[7],
                    frequency=int(p[4]) / 100,
                    course_mag=float(magnetic),
                    course_true=value - magnetic * 360,
                    glideslope=None,
                    category=category,
                )
            else:
                glideslopes[key] = int(value // 1000) / 100
    ils = {}
    for (icao, runway), loc in localizers.items():
        loc.glideslope = glideslopes.get((icao, runway))
        ils.setdefault(icao, {})[runway] = loc
    return ils


def to_local(origin, point):
    """(east, north) of point from origin in nm, flat near the origin"""
    scale = math.cos(math.radians(origin[0]))
    return (point[1] - origin[1]) * 60 * scale, (point[0] - origin[0]) * 60


def from_local(origin, xy):
    scale = math.cos(math.radians(origin[0]))
    return origin[0] + xy[1] / 60, origin[1] + xy[0] / (60 * scale)


def unit(heading):
    return math.sin(math.radians(heading)), math.cos(math.radians(heading))


def vectors(
    lat,
    lon,
    altitude_ft,
    ground_speed_kt,
    variation,
    runway: RunwayEnd,
    speeds: Speeds | None = None,
) -> Vectors:
    """Direct to a join point, a 30 degree intercept, then the final approach.

    variation is magnetic minus true heading at the aircraft, used for legs
    other than the final, whose course comes from the localizer when there is
    one. The intercept leg is flown level at the final's intercept altitude,
    so the direct leg descends to it from altitude_ft, then levels off to slow
    to green dot by the join point. The intercept leg slows to about F speed
    and the final to Vapp by 1000ft. Speeds are taken as ground speeds, with
    the runway headwind taken off the final.
    """
    threshold = (runway.lat, runway.lon)
    final_true = runway.final_true
    ux, uy = unit(final_true)
    intercept = (-FINAL_NM * ux, -FINAL_NM * uy)
    ax, ay = to_local(threshold, (lat, lon))
    # Join final from the side the aircraft is on, turning towards the runway
    side = 1 if ux * ay - uy * ax > 0 else -1
    intercept_true = (final_true + side * INTERCEPT_ANGLE) % 360
    ix, iy = unit(intercept_true)
    join = (intercept[0] - INTERCEPT_NM * ix, intercept[1] - INTERCEPT_NM * iy)

    join_ll = from_local(threshold, join)
    intercept_ll = from_local(threshold, intercept)
    to_join = nm((lat, lon), join_ll)
    legs = [
        Leg("Direct", (course((lat, lon), join_ll) + variation) % 360, to_join),
        Leg("Intercept", (intercept_true + variation) % 360, INTERCEPT_NM),
        Leg("Final", runway.heading_mag(variation), FINAL_NM),
    ]

    angle = runway.ils.glideslope if runway.ils and runway.ils.glideslope else 3.0
    glide_ft_per_nm = math.tan(math.radians(angle)) * 6076
    intercept_alt = runway.elevation_ft + THRESHOLD_HEIGHT + FINAL_NM * glide_ft_per_nm
    intercept_alt = int(round(intercept_alt, -2))
    total = sum(leg.distance for leg in legs)
    moving = ground_speed_kt and ground_speed_kt > 50
    speed = ground_speed_kt if moving else DEFAULT_SPEED_KT

    decel_nm, eta = 0.0, None
    if speeds:
        direct, intercept_leg, final = legs
        # Indicated speed, from true at about 2% more per 1000ft
        indicated = speed / (1 + 0.02 * max(altitude_ft, 0) / 1000)
        gd = min(speeds.green_dot, indicated)
        f_speed = min(INTERCEPT_END_KT, gd)
        decel_nm = min((indicated - gd) * DECEL_NM_PER_KT, to_join)
        direct.speed_kt = gd
        direct.minutes = minutes(to_join - decel_nm, speed, speed) + minutes(
            decel_nm, speed, gd
        )
        intercept_leg.speed_kt = f_speed
        intercept_leg.minutes = minutes(INTERCEPT_NM, gd, f_speed)
        # Slow to Vapp by the stable height, then hold it to the threshold
        stable_nm = min(STABLE_FT / glide_ft_per_nm, FINAL_NM)
        head = speeds.headwind
        final.speed_kt = speeds.vapp
        final.minutes = minutes(
            FINAL_NM - stable_nm, f_speed - head, speeds.vapp - head
        ) + minutes(stable_nm, speeds.vapp - head, speeds.vapp - head)
        if moving:
            eta = sum(leg.minutes for leg in legs)
    elif moving:
        eta = total / ground_speed_kt * 60

    return Vectors(
        legs=legs,
        intercept_alt_ft=intercept_alt,
        glide_angle=angle,
        total_nm=total,
        eta_min=eta,
        points=[(lat, lon), join_ll, intercept_ll, threshold],
        descent=descent_advice(
            altitude_ft - intercept_alt, to_join - decel_nm, speed
        ),
        speeds=speeds,
        decel_nm=decel_nm,
    )


def descent_advice(height_to_lose, distance, ground_speed_kt=None) -> str:
    """When to start down to lose height_to_lose ft within distance nm"""
    if height_to_lose <= 100:
        return ""
    normal = height_to_lose / DESCENT_FT_PER_NM
    if normal < distance:
        return f"start descent in {distance - normal:.0f}nm"
    expedited = height_to_lose / expedite_ft_per_nm(ground_speed_kt)
    if expedited <= distance:
        return "descend now"
    return f"too high, +{expedited - distance:.0f}nm"


class Divert:
    """Nearby airports and runway data for diversions."""

    def __init__(self, generator: Generator):
        self._generator = generator
        self._ils = None
        # Airports an airliner could use, short runways included; requiring an
        # IATA code leaves out private and military fields, which airports-py
        # often marks as having scheduled service
        self._airports = {
            icao: info
            for icao, info in generator.airports.items()
            if info.get("type") in ("large_airport", "medium_airport")
            and (info.get("iata") or generator.board(icao)[0])
        }

    def choices(self):
        """ICAO -> "City IATA (ICAO) name" for the search box, by label"""
        choices = {}
        for icao, info in self._airports.items():
            iata, city = self._generator.board(icao)
            label = " ".join(part for part in (city, iata) if part)
            choices[icao] = f"{label} ({icao}) {info.get('airport', '')}".strip()
        return dict(sorted(choices.items(), key=lambda item: item[1]))

    def ils(self, icao):
        if self._ils is None:
            try:
                self._ils = read_ils(self._generator.paths.earth_nav)
            except OSError:
                self._ils = {}
        return self._ils.get(icao, {})

    def airport(
        self, icao, lat, lon, altitude_ft, ground_speed_kt=None
    ) -> Nearby | None:
        info = self._airports.get(icao) or self._generator.airports.get(icao)
        if info is None:
            return None
        here, there = (lat, lon), (info["latitude"], info["longitude"])
        distance = nm(here, there)
        iata, city = self._generator.board(icao)
        elevation = int(float(info.get("elevation_ft") or 0))
        # Height to lose before the final approach, at an expedited descent
        intercept = elevation + FINAL_NM * DESCENT_FT_PER_NM
        gradient = expedite_ft_per_nm(ground_speed_kt)
        needed = max(0, altitude_ft - intercept) / gradient
        available = max(0, distance - FINAL_NM)
        return Nearby(
            icao=icao,
            iata=iata,
            city=city,
            name=info.get("airport", ""),
            distance=distance,
            bearing_true=course(here, there),
            elevation_ft=elevation,
            too_high_nm=max(0, needed - available),
        )

    def nearby(
        self, lat, lon, altitude_ft, ground_speed_kt=None, count=NEARBY_COUNT
    ) -> list[Nearby]:
        """Closest airports to the aircraft, nearest first"""
        here = (lat, lon)
        close = []
        for icao, info in self._airports.items():
            distance = nm(here, (info["latitude"], info["longitude"]))
            if distance <= NEARBY_RADIUS:
                close.append((distance, icao))
        close.sort()
        return [
            self.airport(icao, lat, lon, altitude_ft, ground_speed_kt)
            for _, icao in close[:count]
        ]

    def runways(self, icao) -> list[RunwayEnd]:
        """Every runway end at the airport from the sim's apt.dat"""
        ends = self._generator.runway_ends(icao)
        ils = self.ils(icao)
        result = []
        for end in ends.values():
            for other in ends.values():
                if other.rwy_idx == end.rwy_idx and other.rwy_dir != end.rwy_dir:
                    hl = heading_and_length(end, other)
                    result.append(
                        RunwayEnd(
                            name=f"RW{end.name}",
                            lat=end.lat,
                            lon=end.lon,
                            length_ft=round(hl.length * M_TO_FT),
                            heading_true=hl.heading,
                            elevation_ft=end.elevation,
                            ils=ils.get(end.name),
                        )
                    )
                    break
        return sorted(result, key=lambda r: r.name)
