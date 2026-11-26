"""Diversions: airports near the aircraft, their runways, and manual vectors
onto the final approach of the chosen runway."""

from dataclasses import dataclass, field
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
# Autobrake target decelerations, m/s²; MAX is for takeoff only
AUTOBRAKE = {"LO": 1.7, "MED": 3.0}
# Threshold to touchdown, and the brakes building up to full decel, m
AIR_DISTANCE_M = 400
BRAKE_DELAY_M = 200
# Margin on the landing distance, and extra on a wet runway
LANDING_MARGIN = 1.15
WET_FACTOR = 1.15
KT_TO_MS = 0.514444
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
    # Already flown
    done: bool = False


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


@dataclass
class Brake:
    # "LO", "MED", or "" when neither fits the runway
    mode: str
    # Distance needed with the margin, ft
    needed_ft: float


def autobrake(vapp, headwind_kt, elevation_ft, length_ft, wet=False) -> Brake:
    """Lowest autobrake whose landing distance, with a margin, fits the
    runway: touchdown at Vapp as true airspeed less the headwind, then the
    autobrake's target decel with no reversers"""
    ground_speed = vapp * (1 + 0.02 * max(elevation_ft, 0) / 1000) - headwind_kt
    v = max(ground_speed, 0) * KT_TO_MS
    factor = LANDING_MARGIN * (WET_FACTOR if wet else 1)
    for mode, decel in AUTOBRAKE.items():
        metres = AIR_DISTANCE_M + BRAKE_DELAY_M + v * v / (2 * decel)
        needed = metres * factor * M_TO_FT
        if needed <= length_ft:
            return Brake(mode, needed)
    return Brake("", needed)


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
    # Map labels of the points after the aircraft
    point_labels: list[str] = field(default_factory=list)
    phase: str = "direct"
    # On final: heading to steer back to the centreline, None when on it, and
    # how far off it the aircraft is, nm, positive to the right
    steer_mag: float | None = None
    off_centreline_nm: float = 0.0


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


# Give around the fixed points when moving on to the next leg, nm: how close
# to the join point, how close to the intercept line once past it, and how
# close to the extended centreline counts as established on final
JOIN_TOLERANCE_NM = 1.5
ON_LINE_NM = 3
ON_FINAL_NM = 1
# How far beyond the intercept point being on the centreline already counts;
# not so far that the join point, close to the converging centreline, counts
EARLY_FINAL_NM = 2
PHASES = ("direct", "intercept", "final")
# Steering onto the centreline: the closing angle is at most the intercept
# angle, aiming no closer than this ahead; on final, aim this far ahead
MIN_LEAD_NM = 1.0
FINAL_LEAD_NM = 2.0
# Off the centreline by less than this counts as on it, nm
ON_CENTRELINE_NM = 0.1


@dataclass
class Route:
    """The diversion's fixed points, worked out once when it starts"""

    threshold: tuple[float, float]
    join: tuple[float, float]
    intercept: tuple[float, float]
    final_true: float
    intercept_true: float


def plan_route(lat, lon, runway: RunwayEnd) -> Route:
    """Join point and intercept point for joining final from the side of the
    extended centreline the aircraft is on, turning towards the runway"""
    threshold = (runway.lat, runway.lon)
    final_true = runway.final_true
    ux, uy = unit(final_true)
    intercept = (-FINAL_NM * ux, -FINAL_NM * uy)
    ax, ay = to_local(threshold, (lat, lon))
    side = 1 if ux * ay - uy * ax > 0 else -1
    intercept_true = (final_true + side * INTERCEPT_ANGLE) % 360
    ix, iy = unit(intercept_true)
    join = (intercept[0] - INTERCEPT_NM * ix, intercept[1] - INTERCEPT_NM * iy)
    return Route(
        threshold=threshold,
        join=from_local(threshold, join),
        intercept=from_local(threshold, intercept),
        final_true=final_true,
        intercept_true=intercept_true,
    )


def next_phase(route: Route, lat, lon, phase="direct") -> str:
    """The leg being flown, moving only forwards, with some give around the
    join point, the intercept line and the extended centreline"""
    thr = route.threshold
    ax, ay = to_local(thr, (lat, lon))
    jx, jy = to_local(thr, route.join)
    ux, uy = unit(route.final_true)
    ix, iy = unit(route.intercept_true)

    # Distance out on the approach side, and off the extended centreline
    out = -(ax * ux + ay * uy)
    off_final = abs(ux * ay - uy * ax)
    on_final = 0 < out <= FINAL_NM + EARLY_FINAL_NM and off_final <= ON_FINAL_NM
    past_intercept = 0 < out < FINAL_NM and off_final <= ON_LINE_NM
    if phase == "final" or on_final or past_intercept:
        return "final"

    # Along and off the intercept line, measured from the join point
    along = (ax - jx) * ix + (ay - jy) * iy
    off_line = abs(ix * (ay - jy) - iy * (ax - jx))
    near_join = math.hypot(ax - jx, ay - jy) <= JOIN_TOLERANCE_NM
    if phase == "intercept" or near_join or (along > 0 and off_line <= ON_LINE_NM):
        return "intercept"
    return "direct"


def vectors(
    lat,
    lon,
    altitude_ft,
    ground_speed_kt,
    variation,
    runway: RunwayEnd,
    speeds: Speeds | None = None,
    route: Route | None = None,
    phase="direct",
) -> Vectors:
    """Direct to a join point, a 30 degree intercept, then the final approach,
    from the leg being flown; legs already flown have no distance and are done.

    variation is magnetic minus true heading at the aircraft, used for legs
    other than the final, whose course comes from the localizer when there is
    one. The intercept leg is flown level at the final's intercept altitude,
    so the direct leg descends to it from altitude_ft, then levels off to slow
    to green dot by the join point. The intercept leg slows to about F speed
    and the final to Vapp by 1000ft. Speeds are taken as ground speeds, with
    the runway headwind taken off the final.
    """
    route = route or plan_route(lat, lon, runway)
    here = (lat, lon)
    step = PHASES.index(phase)
    # Where the aircraft is against the extended centreline: distance out on
    # the approach side, and off it, positive to the right
    thr = route.threshold
    ux, uy = unit(route.final_true)
    ax, ay = to_local(thr, here)
    out = -(ax * ux + ay * uy)
    off_right = -(ux * ay - uy * ax)

    def centreline(distance_out):
        return from_local(thr, (-distance_out * ux, -distance_out * uy))

    to_join = nm(here, route.join) if step == 0 else 0.0
    intercept_heading = (route.intercept_true + variation) % 360
    steer_mag = None
    if step == 0:
        to_intercept = INTERCEPT_NM
        to_threshold = FINAL_NM
    elif step == 1:
        # Head for the centreline ahead, closing at no more than the
        # intercept angle, from wherever the join point was passed
        lead = max(abs(off_right) / math.tan(math.radians(INTERCEPT_ANGLE)), MIN_LEAD_NM)
        aim_out = max(out - lead, 0)
        aim = centreline(aim_out)
        intercept_heading = (course(here, aim) + variation) % 360
        to_intercept = nm(here, aim)
        to_threshold = aim_out
    else:
        to_intercept = 0.0
        to_threshold = nm(here, thr)
        # Off the centreline on final: steer for it a little ahead
        if abs(off_right) >= ON_CENTRELINE_NM:
            aim = centreline(max(out - FINAL_LEAD_NM, 0))
            steer_mag = (course(here, aim) + variation) % 360
    legs = [
        Leg("Direct", (course(here, route.join) + variation) % 360, to_join),
        Leg("Intercept", intercept_heading, to_intercept),
        Leg("Final", runway.heading_mag(variation), to_threshold),
    ]
    for leg in legs[:step]:
        leg.done = True

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
        intercept_leg.minutes = minutes(to_intercept, gd, f_speed)
        # Slow to Vapp by the stable height, then hold it to the threshold
        stable_nm = min(STABLE_FT / glide_ft_per_nm, to_threshold)
        head = speeds.headwind
        final_start = f_speed if step < 2 else min(f_speed, indicated)
        final.speed_kt = speeds.vapp
        final.minutes = minutes(
            to_threshold - stable_nm, final_start - head, speeds.vapp - head
        ) + minutes(stable_nm, speeds.vapp - head, speeds.vapp - head)
        if moving:
            eta = sum(leg.minutes for leg in legs)
    elif moving:
        eta = total / ground_speed_kt * 60

    # The intercept leg is level, so the descent ends where it starts
    if step == 0:
        descent = descent_advice(altitude_ft - intercept_alt, to_join - decel_nm, speed)
    elif step == 1:
        descent = descent_advice(altitude_ft - intercept_alt, to_intercept, speed)
    else:
        descent = ""
    fixed = [route.join, route.intercept, route.threshold][step:]
    return Vectors(
        legs=legs,
        intercept_alt_ft=intercept_alt,
        glide_angle=angle,
        total_nm=total,
        eta_min=eta,
        points=[here] + fixed,
        point_labels=["JOIN", "FINAL", "RWY"][step:],
        descent=descent,
        speeds=speeds,
        decel_nm=decel_nm,
        phase=phase,
        steer_mag=steer_mag,
        off_centreline_nm=off_right,
    )


# How far off the glide path counts as on it, and as well off it, ft
ON_PATH_FT = 100
WELL_OFF_PATH_FT = 600


@dataclass
class GlideCheck:
    distance: float
    # Above the runway, and where the glide path is at this distance, ft
    height: float
    path: float
    angle: float
    # Vertical speed to reach the threshold from here, and to stay on the
    # path, fpm; None when not moving
    vs_needed: float | None
    vs_on_path: float | None

    @property
    def off(self):
        """Above the path, ft; negative when below it"""
        return self.height - self.path

    @property
    def where(self):
        if abs(self.off) < ON_PATH_FT:
            return "on path"
        return f"{abs(self.off):.0f}ft {'high' if self.off > 0 else 'low'}"

    @property
    def text(self):
        text = (
            f"{self.distance:.1f}nm, {self.height:.0f}ft above, "
            f"{self.angle:.1f}° path {self.path:.0f}ft: {self.where}"
        )
        if self.vs_needed is not None:
            text += f"; VS {self.vs_needed:.0f}fpm, on path {self.vs_on_path:.0f}fpm"
        return text


def glide_check(lat, lon, altitude_ft, ground_speed_kt, runway: RunwayEnd) -> GlideCheck:
    """Height against the glide path to the threshold, and the VS to stay on
    it; distance is direct to the threshold, so only meaningful on final"""
    angle = runway.ils.glideslope if runway.ils and runway.ils.glideslope else 3.0
    glide_ft_per_nm = math.tan(math.radians(angle)) * 6076
    distance = nm((lat, lon), (runway.lat, runway.lon))
    height = altitude_ft - runway.elevation_ft
    vs_needed = vs_on_path = None
    if ground_speed_kt and ground_speed_kt > 50 and distance > 0.3:
        vs_needed = max(height - THRESHOLD_HEIGHT, 0) * ground_speed_kt / (60 * distance)
        vs_on_path = ground_speed_kt * glide_ft_per_nm / 60
    return GlideCheck(
        distance=distance,
        height=height,
        path=THRESHOLD_HEIGHT + distance * glide_ft_per_nm,
        angle=angle,
        vs_needed=vs_needed,
        vs_on_path=vs_on_path,
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
    # Rounded up, so a small shortfall never reads +0nm
    return f"too high, +{math.ceil(expedited - distance)}nm"


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
        elevation = self._generator.field_elevation(icao)
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
