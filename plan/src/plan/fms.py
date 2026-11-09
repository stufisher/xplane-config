from dataclasses import dataclass
import logging
import os
from typing import Optional

from airports.airport_data import get_airport_by_icao
from nicegui import run

from .apt import APT

DEFAULT_FMS_PATH = os.path.expanduser("~/X-Plane 12/Output/FMS Plans")
DEFAULT_CIFP_PATH = os.path.expanduser("~/X-Plane 12/Resources/default data/CIFP")
DEFAULT_EARTH_FIX_PATH = os.path.expanduser(
    "~/X-Plane 12/Resources/default data/earth_fix.dat"
)
DEFAULT_EARTH_NAV_PATH = os.path.expanduser(
    "~/X-Plane 12/Resources/default data/earth_nav.dat"
)

logger = logging.getLogger(__name__)


@dataclass
class Waypoint:
    type_id: int
    name: str
    latitude: float
    longitude: float
    type: Optional[str] = None
    altitude: Optional[float] = None


@dataclass
class Procedure:
    name: str
    type: str
    runway: str
    airport: str
    waypoints: list[Waypoint]


@dataclass
class FMSPlan:
    file_path: str
    CYCLE: str
    NUMENR: int

    departure: str
    ADEP: str
    ADES: str
    destination: str

    waypoints: list[Waypoint]

    DEPRWY: Optional[str] = None
    DEPRWY_LENGTH: Optional[int] = None
    SID: Optional[str] = None

    STAR: Optional[str] = None
    APP: Optional[str] = None
    DESRWY: Optional[str] = None
    DESRWY_LENGTH: Optional[int] = None

    sid_proc: Optional[Procedure] = None
    star_proc: Optional[Procedure] = None
    app_proc: Optional[Procedure] = None

    async def load_procedures(self, cifp, apt: APT, load_runway: bool):
        logger.info(f"Loading procedures for {self.ADEP} to {self.ADES}")
        if self.SID and self.sid_proc is None:
            self.sid_proc = await cifp.get_procedure(self.SID, self.ADEP, self.DEPRWY)
        if self.STAR and self.star_proc is None:
            self.star_proc = await cifp.get_procedure(self.STAR, self.ADES, self.DESRWY)
        if self.APP and self.app_proc is None:
            self.app_proc = await cifp.get_procedure(self.APP, self.ADES)

        if load_runway:
            logger.info("Loading runway data")
            if self.DEPRWY and self.DEPRWY_LENGTH is None:
                hdg_len = await apt.get_runway_heading_and_length(
                    self.ADEP, self.DEPRWY
                )
                self.DEPRWY_LENGTH = int(hdg_len.length * 3.28084)
            if self.DESRWY and self.DESRWY_LENGTH is None:
                hdg_len = await apt.get_runway_heading_and_length(
                    self.ADES, self.DESRWY
                )
                self.DESRWY_LENGTH = int(hdg_len.length * 3.28084)
        logger.info("Done loading")

    @property
    def segments(self) -> list[tuple[str, list[Waypoint]]]:
        """Waypoints grouped by leg, ordered from departure to arrival."""
        legs = [
            ("SID", self.sid_proc.waypoints if self.sid_proc else []),
            ("ENRT", self.waypoints),
            ("STAR", self.star_proc.waypoints if self.star_proc else []),
            ("APP", self.app_proc.waypoints if self.app_proc else []),
        ]
        return [(name, waypoints) for name, waypoints in legs if waypoints]


def get_waypoint(waypoint_and_type: list[str], icao_code: str = None):
    waypoint = waypoint_and_type[0]
    type_id = int(waypoint_and_type[1])
    is_dme = int(waypoint_and_type[2])

    found_waypoints = []
    if not is_dme:
        with open(DEFAULT_EARTH_FIX_PATH) as earth_fix_file:
            for _ in range(3):
                next(earth_fix_file)
            for line in earth_fix_file:
                cols = line.split()
                if len(cols) < 5:
                    continue
                if cols[2] == waypoint:
                    found_waypoints.append([cols[0], cols[1], cols[3]])

    # Waypoint might be a VOR/DME
    if not found_waypoints:
        with open(DEFAULT_EARTH_NAV_PATH) as earth_nav_file:
            for _ in range(3):
                next(earth_nav_file)
            for line in earth_nav_file:
                cols = line.split()
                if len(cols) < 10:
                    continue
                if cols[7] == waypoint:
                    found_waypoints.append([cols[1], cols[2], cols[3]])

    if not found_waypoints:
        return

    matched_waypoint = found_waypoints[0]
    if len(found_waypoints) > 1:
        for found_waypoint in found_waypoints:
            if found_waypoint[2] != "ENRT" and found_waypoint[2] == icao_code:
                matched_waypoint = found_waypoint

    return Waypoint(
        type_id=type_id,
        name=waypoint,
        latitude=float(matched_waypoint[0]),
        longitude=float(matched_waypoint[1]),
    )


def normalise_runway(name: str):
    return name.strip().removeprefix("RW") if name else ""


def runway_matches(name: str, wanted: str):
    """Whether a CIFP runway or transition identifier covers the runway wanted.

    A trailing B stands for every parallel runway with that number, so RW04B is
    flown from 04L, 04C and 04R alike.
    """
    name = normalise_runway(name)
    wanted = normalise_runway(wanted)
    if name.endswith("B"):
        return name[:-1] == wanted[:2]
    return name == wanted


def parse_procedure(procedure_name: str, icao_code: str):
    """Return the procedure's legs grouped by transition, its runways and its type.

    A procedure name covers several alternative routes: one set of legs per
    departure/arrival runway, plus one per enroute transition. They are keyed by
    the transition identifier, which holds either a runway (RW04) or the fix the
    transition ends at, so the caller can pick the route actually being flown.
    """
    file_path = os.path.join(DEFAULT_CIFP_PATH, f"{icao_code}.dat")
    transitions = {}
    complete = set()
    runways = {}
    found_procedure_type = None
    with open(file_path) as cifp_file:
        for line in cifp_file:
            procedure_type, procedure_details_orig = line.split(":")
            procedure_details = procedure_details_orig.split(",")

            if procedure_type == "RWY":
                runway_name = procedure_details[0].strip()
                runway_details = procedure_details_orig.split(";")
                runway_coords = runway_details[1].split(",")
                runways[runway_name] = Waypoint(
                    type_id=1,
                    name=runway_name,
                    latitude=dms2deg(runway_coords[0]),
                    longitude=dms2deg(runway_coords[1]),
                )
                continue

            if procedure_details[2] != procedure_name:
                continue
            # Route type A rows are the feeder transitions, not the approach itself
            if procedure_type == "APPCH" and procedure_details[1] == "A":
                continue

            found_procedure_type = procedure_type
            transition = procedure_details[3].strip()
            if transition in complete:
                continue

            legs = transitions.setdefault(transition, [])
            # Legs such as VI fly a heading rather than to a fix, so plot nothing.
            # Successive legs can share a fix, which would stack markers on it.
            fix = procedure_details[4].strip()
            if fix and (not legs or legs[-1].split(",")[0] != fix):
                is_dme = "1" if procedure_details[6] == "D" else "0"
                legs.append(f"{fix},1,{is_dme}")

            # An approach ends at the missed approach point, flagged in the
            # waypoint description code; the legs after it fly the miss
            description = procedure_details[8]
            if procedure_type == "APPCH" and description[3:4] == "M":
                complete.add(transition)

    return transitions, runways, found_procedure_type


def select_transition(transitions: dict, plan_runway: str = None):
    """Pick the legs flown from plan_runway, dropping the other runways' routes."""
    if plan_runway:
        for transition, legs in transitions.items():
            if runway_matches(transition, plan_runway):
                return transition, legs
    # Approaches hold their legs under a blank transition identifier
    if "" in transitions:
        return "", transitions[""]
    if len(transitions) == 1:
        return next(iter(transitions.items()))
    return None, []


class CIFP:
    def __init__(self):
        self._waypoint_cache = {}
        self._procedure_cache = {}
        self._runways_cache = {}

    async def get_waypoint(self, waypoint_and_type: str, icao_code: str = None):
        waypoint_and_type = waypoint_and_type.split(",")
        waypoint = waypoint_and_type[0]
        waypoint_key = f"{waypoint}-{icao_code}"
        if waypoint_key in self._waypoint_cache:
            return self._waypoint_cache[waypoint_key]

        wpt = await run.cpu_bound(get_waypoint, waypoint_and_type, icao_code)
        self._waypoint_cache[waypoint_key] = wpt
        return wpt

    async def get_procedure(
        self, procedure_name: str, icao_code: str, plan_runway: str = None
    ):
        procedure_key = f"{procedure_name}-{icao_code}-{plan_runway}"
        if procedure_key in self._procedure_cache:
            return self._procedure_cache[procedure_key]

        transitions, runways, found_procedure_type = await run.cpu_bound(
            parse_procedure, procedure_name, icao_code
        )
        self._runways_cache[icao_code] = runways

        runway, procedure_waypoints = select_transition(transitions, plan_runway)
        if runway is None:
            logger.warning(
                f"No {procedure_name} legs for {icao_code} {plan_runway}, "
                f"have {sorted(transitions)}"
            )

        waypoints = []
        for waypoint in procedure_waypoints:
            wpt = await self.get_waypoint(waypoint, icao_code)
            if not wpt:
                waypoint_and_type = waypoint.split(",")
                wpt = runways.get(waypoint_and_type[0], None)
            if not wpt:
                logger.warning(f"Could not lookup waypoint {waypoint} {icao_code}")
                continue
            waypoints.append(wpt)

        # A SID starts at the runway threshold, an arrival procedure ends there
        for runway_name, threshold in runways.items():
            if plan_runway and runway_matches(runway_name, plan_runway):
                if found_procedure_type == "SID":
                    waypoints.insert(0, threshold)
                else:
                    waypoints.append(threshold)
                break

        proc = Procedure(
            name=procedure_name,
            runway=runway,
            type=found_procedure_type,
            airport=icao_code,
            waypoints=waypoints,
        )
        self._procedure_cache[procedure_key] = proc
        return proc


def dms2deg(dms: str):
    # N46134023
    if dms.startswith("N") or dms.startswith("S"):
        deg = int(dms[1:3])
        min = int(dms[3:5])
        sec = float(f"{dms[5:7]}.{dms[7:9]}")
        deg = (deg + min / 60 + sec / 3600) * (-1 if dms[0] == "S" else 1)

    # E006053824
    else:
        deg = int(dms[1:4])
        min = int(dms[4:6])
        sec = float(f"{dms[6:8]}.{dms[8:10]}")
        deg = (deg + min / 60 + sec / 3600) * (-1 if dms[0] == "W" else 1)

    return float(deg)


def decdeg2dms(dd):
    negative = dd < 0
    dd = abs(dd)
    minutes, seconds = divmod(dd * 3600, 60)
    degrees, minutes = divmod(minutes, 60)
    if negative:
        if degrees > 0:
            degrees = -degrees
        elif minutes > 0:
            minutes = -minutes
        else:
            seconds = -seconds
    return (int(degrees), int(minutes), round(seconds))


def latlon_to_fms(lat: float, lon: float):
    lat_dms = decdeg2dms(lat)
    lon_dms = decdeg2dms(lon)

    return f"{lat_dms[0]:02d}{lat_dms[1]:02d}.{lat_dms[2]:02d}N/{lon_dms[0]:03d}{lon_dms[1]:02d}.{lon_dms[2]:02d}E"


class FMS:
    def __init__(self, apt: APT, path=None):
        self._apt = apt
        self._cifp = CIFP()
        self._path = path if path is not None else DEFAULT_FMS_PATH
        self._plans: list[FMSPlan] = []
        self._update_plans()

    def _parse_plan(self, file_path: str):
        with open(file_path) as file:
            fms = {"waypoints": [], "file_path": file_path}
            in_waypoints = False
            for _ in range(2):
                next(file)
            for line in file:
                line = line.strip()
                if in_waypoints:
                    wpt = line.split(" ")
                    fms["waypoints"].append(
                        Waypoint(
                            type_id=int(wpt[0]),
                            name=wpt[1],
                            type=wpt[2],
                            altitude=float(wpt[3]),
                            latitude=float(wpt[4]),
                            longitude=float(wpt[5]),
                        )
                    )
                else:
                    key, value = line.split(" ")
                    fms[key] = value
                    if key == "NUMENR":
                        in_waypoints = True

            fms["departure"] = get_airport_by_icao(fms["ADEP"])[0]["airport"]
            fms["destination"] = get_airport_by_icao(fms["ADES"])[0]["airport"]
            return FMSPlan(**fms)

    def _update_plans(self):
        self._plans = []
        for file_name in os.listdir(self._path):
            if file_name.endswith(".fms"):
                file_path = os.path.join(self._path, file_name)
                plan = self._parse_plan(file_path)
                self._plans.append(plan)

    @property
    def plans(self):
        self._update_plans()
        return self._plans

    async def get_plan(self, file_path: str, load_runway: bool):
        for plan in self.plans:
            if plan.file_path == file_path:
                await plan.load_procedures(self._cifp, self._apt, load_runway)
                return plan


if __name__ == "__main__":
    # fms = FMS()

    # coords = (45.435120, 6.687012)
    # lat = decdeg2dms(coords[0])
    # lon = decdeg2dms(coords[1])
    # print(lat, lon)
    # sp = latlon_to_fms(*coords)
    # print(sp)

    cifp = CIFP()
    proc = cifp.get_procedure("BENO1R", "LSGG")
    print(proc)
    proc = cifp.get_procedure("I04", "LSGG")
    print(proc)

    # lat = dms2deg("N46134023")
    # lon = dms2deg("E006053824")
    # print(lat, lon)
