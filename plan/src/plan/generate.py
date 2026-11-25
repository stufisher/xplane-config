"""Generate X-Plane 1100 .fms flight plans from the sim's own navdata.

Runway, SID, airway route, STAR and approach all come from the same AIRAC
cycle as the sim, so every procedure and fix a plan names exists there.
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import heapq
import math
import os
import re
import threading

from airports.airport_data import airports as AIRPORTS

from .apt import longest_runway_m
from .fms import dms2deg, runway_matches
from .places import Places, download_missing
from .xplane import DEFAULT_XPLANE_DIR, XPlanePaths

# Runway choice without wind or history faces the prevailing wind over Europe
PREVAILING_WIND = 250
# Below this many knots the wind does not decide the runway
MIN_WIND_KT = 5
# Climb and descent gradient for the altitude profile, ft per nm (~3 degrees)
GRADIENT = 318
# Direct legs between waypoints bridge free route airspace where the data has
# no airways; the cost factor keeps airways preferred wherever they exist
DCT_RADIUS = 150
DCT_FACTOR = 1.5
# Cost of switching airway, nm, so routes stay on one airway like filed routes
AIRWAY_CHANGE = 20
# Approach types in order of preference, by the first letter of its name
APP_PREFERENCE = {"I": 0, "R": 1, "H": 1, "J": 1, "L": 2, "X": 2, "G": 2}
# Block time estimate: taxi and climb allowance plus cruise at 450 kt
BLOCK_ALLOWANCE_MIN = 20
CRUISE_NM_PER_MIN = 7.5

KIND_FIX, KIND_VOR, KIND_NDB = 11, 3, 2


def nm(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 3440.065 * 2 * math.asin(math.sqrt(h))


def course(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(
        lo2 - lo1
    )
    return math.degrees(math.atan2(y, x)) % 360


def angle_diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def runway_heading(runway):
    return int(runway[2:4]) * 10


def runway_score(length_ft):
    """Difficulty added by a short longest runway, 0 when long or unknown"""
    if not length_ft:
        return 0
    return 3 if length_ft < 5000 else 2 if length_ft < 6000 else 1 if length_ft < 7000 else 0


def block_minutes(distance):
    return BLOCK_ALLOWANCE_MIN + distance / CRUISE_NM_PER_MIN


def cruise_levels(distance, initial_course):
    """Semicircular levels to try, odd eastbound and even westbound, in feet.

    Short hops stay at FL200-FL250 so the flight is not all climb and descent.
    """
    east = initial_course < 180
    if distance < 120:
        levels = [170] if east else [180]
    else:
        levels = [210, 230, 250] if east else [200, 220, 240]
    return [fl * 100 for fl in levels]


class NavDB:
    """Fixes, navaids and the airway graph from the earth_*.dat files."""

    def __init__(self, paths: XPlanePaths):
        self.cycle = "0000"
        self.fixes = defaultdict(list)
        with open(paths.earth_fix) as f:
            for line in f:
                p = line.split()
                if len(p) < 5:
                    continue
                try:
                    lat, lon = float(p[0]), float(p[1])
                except ValueError:
                    continue
                self.fixes[(p[2], p[4])].append((lat, lon, p[3]))

        # DME rows only fill in where no VOR or NDB row exists
        self.navaids = {}
        with open(paths.earth_nav) as f:
            for line in f:
                p = line.split()
                if len(p) < 10 or p[0] not in ("2", "3", "12", "13"):
                    continue
                kind = KIND_NDB if p[0] == "2" else KIND_VOR
                key = (p[7], p[9], kind)
                if p[0] in ("2", "3") or key not in self.navaids:
                    self.navaids[key] = (float(p[1]), float(p[2]))

        # node -> {neighbour: [(airway, base ft, top ft)]}; a segment can be
        # listed once as a low and once as a high airway with different bands
        self.graph = defaultdict(lambda: defaultdict(list))
        with open(paths.earth_awy) as f:
            for line in f:
                cycle = re.search(r"data cycle (\d{4})", line)
                if cycle:
                    self.cycle = cycle.group(1)
                p = line.split()
                if len(p) < 11 or not p[2].isdigit():
                    continue
                a = (p[0], p[1], int(p[2]))
                b = (p[3], p[4], int(p[5]))
                seg = (p[10], int(p[8]) * 100, int(p[9]) * 100)
                self.graph[a][b].append(seg)
                if p[6] == "N":
                    self.graph[b][a].append(seg)

        self.pos = {}
        for node in list(self.graph):
            self.position(node)

    def position(self, node, airport=None):
        if node in self.pos and airport is None:
            return self.pos[node]
        ident, region, kind = node
        found = None
        if kind in (KIND_VOR, KIND_NDB):
            found = self.navaids.get(node) or self.navaids.get(
                (ident, region, KIND_VOR if kind == KIND_NDB else KIND_NDB)
            )
        if found is None:
            rows = self.fixes.get((ident, region), [])
            rows = sorted(rows, key=lambda r: (r[2] != airport, r[2] != "ENRT"))
            if rows:
                found = rows[0][:2]
        if found is None:
            found = self.navaids.get((ident, region, KIND_VOR)) or self.navaids.get(
                (ident, region, KIND_NDB)
            )
        if airport is None:
            self.pos[node] = found
        return found

    def graph_node(self, ident, region, kind):
        """Airway node for a procedure fix, whatever kind the airway lists it as."""
        for k in (kind, KIND_FIX, KIND_VOR, KIND_NDB):
            if (ident, region, k) in self.graph:
                return (ident, region, k)
        return (ident, region, kind)


class Airport:
    """Position from airports-py, runways and procedures from its CIFP file."""

    def __init__(self, icao, info, nav, cifp_dir):
        self.icao = icao
        self.lat = float(info["latitude"])
        self.lon = float(info["longitude"])
        self.runways = {}
        # Threshold elevations; the airports-py elevation field is unreliable
        self.runway_elevations = {}
        # kind -> name -> transition -> [(ident, region, kind)]
        self.procs = {"SID": {}, "STAR": {}, "APPCH": {}}
        self._nav = nav
        path = os.path.join(cifp_dir, f"{icao}.dat")
        if os.path.exists(path):
            self._parse(path)
        self.elev = max(self.runway_elevations.values(), default=0)

    def _parse(self, path):
        complete = set()
        with open(path) as f:
            for line in f:
                kind, _, rest = line.partition(":")
                p = rest.split(",")
                if kind == "RWY":
                    name = p[0].strip()
                    # Some runways have no threshold position, use the airport's
                    coords = rest.split(";")[1].split(",")
                    try:
                        threshold = (dms2deg(coords[0]), dms2deg(coords[1]))
                    except (ValueError, IndexError):
                        threshold = (self.lat, self.lon)
                    self.runways[name] = threshold
                    if p[3].strip().isdigit():
                        self.runway_elevations[name] = int(p[3])
                    continue
                if kind not in self.procs or len(p) < 9:
                    continue
                route_type, name, trans = p[1], p[2], p[3].strip()
                # Engine-out SIDs are not a departure route
                if kind == "SID" and route_type == "0":
                    continue
                if kind == "APPCH" and route_type != "A":
                    trans = ""
                key = (name, trans)
                if key in complete:
                    continue
                ident, region, section, sub = p[4].strip(), p[5].strip(), p[6], p[7]
                legs = self.procs[kind].setdefault(name, {}).setdefault(trans, [])
                if ident and (not legs or legs[-1][0] != ident):
                    if section == "P" and sub == "G":
                        fix_kind = "RWY"
                    elif section == "D":
                        fix_kind = KIND_NDB if sub == "B" else KIND_VOR
                    elif section == "P" and sub == "N":
                        fix_kind = KIND_NDB
                    else:
                        fix_kind = KIND_FIX
                    legs.append((ident, region, fix_kind))
                # Legs after the missed approach point fly the miss
                if kind == "APPCH" and p[8][3:4] == "M":
                    complete.add(key)

    @property
    def pos(self):
        return (self.lat, self.lon)

    def fix_pos(self, leg):
        if leg[2] == "RWY":
            return self.runways.get(leg[0]) or self.pos
        return self._nav.position(leg, self.icao) or self.pos

    def path_length(self, legs, start=None):
        points = ([start] if start else []) + [self.fix_pos(leg) for leg in legs]
        return sum(nm(a, b) for a, b in zip(points, points[1:]))

    @staticmethod
    def _split(transitions, runway):
        """Runway, common and enroute parts of a SID or STAR; None if runway unserved."""
        rw = {t: legs for t, legs in transitions.items() if t.startswith("RW")}
        common = transitions.get("", []) or transitions.get("ALL", [])
        enroute = {
            t: legs
            for t, legs in transitions.items()
            if t not in rw and t not in ("", "ALL")
        }
        rw_legs = []
        if rw:
            match = [t for t in rw if runway_matches(t, runway)]
            if not match:
                return None
            rw_legs = rw[match[0]]
        return rw_legs, common, enroute

    def sid_options(self, runway):
        """(name, procedure legs, transition legs flown as plain waypoints)."""
        options = []
        for name, transitions in self.procs["SID"].items():
            split = self._split(transitions, runway)
            if split is None:
                continue
            rw_legs, common, enroute = split
            base = rw_legs + [leg for leg in common if not rw_legs or leg != rw_legs[-1]]
            if not base and not enroute:
                continue
            if base or not enroute:
                options.append((name, base, []))
            for legs in enroute.values():
                extra = [leg for leg in legs if not base or leg != base[-1]]
                options.append((name, base, extra))
        return [o for o in options if o[1] or o[2]]

    def star_options(self, runway):
        """(name, transition legs flown as plain waypoints, procedure legs)."""
        options = []
        for name, transitions in self.procs["STAR"].items():
            split = self._split(transitions, runway)
            if split is None:
                continue
            rw_legs, common, enroute = split
            base = common + [leg for leg in rw_legs if not common or leg != common[-1]]
            if base:
                options.append((name, [], base))
            for legs in enroute.values():
                extra = [leg for leg in legs if not base or leg != base[0]]
                options.append((name, extra, base))
        return [o for o in options if o[1] or o[2]]

    def approaches(self, runway):
        """Approaches to runway, most preferred first."""
        found = []
        for name, transitions in self.procs["APPCH"].items():
            m = re.match(r"^([A-Z])(\d{2}[LCR]?)", name)
            if not m or m.group(2) != runway.removeprefix("RW"):
                continue
            found.append((APP_PREFERENCE.get(m.group(1), 3), name, transitions))
        found.sort(key=lambda a: (a[0], a[1]))
        return found


def plan_headers(plan_dir):
    """Header keys of every .fms plan in plan_dir."""
    headers = []
    if not os.path.isdir(plan_dir):
        return headers
    for file_name in os.listdir(plan_dir):
        if not file_name.endswith(".fms"):
            continue
        head = {}
        with open(os.path.join(plan_dir, file_name)) as f:
            for line in f:
                p = line.split()
                if len(p) == 2:
                    head[p[0]] = p[1]
        headers.append(head)
    return headers


@dataclass
class Destination:
    icao: str
    iata: str
    city: str
    distance: float
    minutes: float
    # Already appears in one of the existing plans
    known: bool


@dataclass
class GeneratedPlan:
    adep: str
    ades: str
    text: str
    summary: str


class Generator:
    """Plans routes on the sim's navdata, which is loaded on first use."""

    def __init__(self, paths: XPlanePaths = XPlanePaths(), places: Places = None):
        self._paths = paths
        self._places = places or Places()
        self._nav = None
        self._runway_lengths = {}
        # The UI plans from worker threads, the navdata must only load once
        self._nav_lock = threading.Lock()
        self._airports = {}
        for info in AIRPORTS:
            if info.get("icao"):
                self._airports.setdefault(info["icao"], info)
        # Airports worth flying to: scheduled service and procedures in the sim
        self._candidates = [
            icao
            for icao, info in self._airports.items()
            if info.get("type") in ("large_airport", "medium_airport")
            and info.get("scheduled_service") == "TRUE"
            and info.get("iata")
            and os.path.exists(os.path.join(paths.cifp, f"{icao}.dat"))
        ]

    @property
    def nav(self):
        with self._nav_lock:
            if self._nav is None:
                self._nav = NavDB(self._paths)
        return self._nav

    def airport(self, icao):
        info = self._airports.get(icao)
        if info is None:
            raise KeyError(f"Unknown airport {icao}")
        return Airport(icao, info, self.nav, self._paths.cifp)

    def _usage(self):
        """How often each airport's runways appear in the existing plans."""
        usage = Counter()
        for head in plan_headers(self._paths.fms_plans):
            if "ADEP" in head and "DEPRWY" in head:
                usage[(head["ADEP"], head["DEPRWY"])] += 1
            if "ADES" in head and "DESRWY" in head:
                usage[(head["ADES"], head["DESRWY"])] += 1
        return usage

    def board(self, icao):
        """IATA code and city as plan-ui shows them, each '' when unknown."""
        place = self._places.lookup(icao)
        info = self._airports.get(icao, {})
        return place.iata or info.get("iata") or "", place.city or ""

    def nearest_airport(self, lat, lon):
        """Closest airport with scheduled service and procedures in the sim."""
        if not self._candidates:
            return None
        return min(
            self._candidates,
            key=lambda icao: nm(
                (lat, lon),
                (self._airports[icao]["latitude"], self._airports[icao]["longitude"]),
            ),
        )

    def destinations(self, adep, min_minutes=60, max_minutes=90):
        """Airports within the block time range, shortest first."""
        info = self._airports.get(adep)
        if info is None:
            raise KeyError(f"Unknown airport {adep}")
        origin = (info["latitude"], info["longitude"])
        known = set()
        for head in plan_headers(self._paths.fms_plans):
            known.update(head.get(k) for k in ("ADEP", "ADES"))
        found = []
        for icao in self._candidates:
            if icao == adep:
                continue
            other = self._airports[icao]
            distance = nm(origin, (other["latitude"], other["longitude"]))
            minutes = block_minutes(distance)
            if min_minutes <= minutes <= max_minutes:
                iata, city = self.board(icao)
                found.append(
                    Destination(icao, iata, city, distance, minutes, icao in known)
                )
        return sorted(found, key=lambda d: d.minutes)

    def runways(self, icao):
        return sorted(self.airport(icao).runways)

    def longest_runway_ft(self, icao):
        """Longest runway in the sim's apt.dat, None when unknown"""
        if icao not in self._runway_lengths:
            try:
                metres = longest_runway_m(self._paths.apt, icao)
            except OSError:
                metres = None
            self._runway_lengths[icao] = round(metres * 3.28084) if metres else None
        return self._runway_lengths[icao]

    def approaches(self, icao, runway):
        """Approach names to runway, most preferred (ILS, then RNAV) first."""
        return [name for _, name, _ in self.airport(icao).approaches(runway)]

    def default_runway(self, icao, arrival, wind=None):
        return self._pick_runway(self.airport(icao), arrival, wind)

    def _pick_runway(self, apt, arrival, wind=None):
        """Into a real wind first, then the runway used most, then prevailing wind.

        wind is (direction degrees, speed kt), or None when unknown.
        """
        if not apt.runways:
            return None

        def procedures_penalty(rw):
            if arrival:
                apps = apt.approaches(rw)
                return [0, 20, 45, 60][apps[0][0]] if apps else 90
            return 0 if apt.sid_options(rw) else 90

        if wind and wind[0] is not None and wind[1] >= MIN_WIND_KT:
            return min(
                apt.runways,
                key=lambda rw: angle_diff(runway_heading(rw), wind[0])
                + procedures_penalty(rw),
            )
        used = [
            (n, rw)
            for (icao, rw), n in self._usage().items()
            if icao == apt.icao and rw in apt.runways
        ]
        if used:
            return max(used)[1]
        return min(
            apt.runways,
            key=lambda rw: angle_diff(runway_heading(rw), PREVAILING_WIND)
            + procedures_penalty(rw),
        )

    def plan(
        self, adep, ades, dep_rwy=None, des_rwy=None, cruise_fl=None, approach=None
    ):
        """Build a plan; runways, approach and cruise level are chosen when not given.

        The STAR is picked to end where the approach starts.
        """
        nav = self.nav
        dep, des = self.airport(adep), self.airport(ades)
        dep_rwy = dep_rwy or self._pick_runway(dep, arrival=False)
        des_rwy = des_rwy or self._pick_runway(des, arrival=True)
        for apt, rw in ((dep, dep_rwy), (des, des_rwy)):
            if rw and rw not in apt.runways:
                raise ValueError(f"{apt.icao} has no runway {rw}")
        direct = nm(dep.pos, des.pos)

        def in_corridor(p):
            return p and nm(dep.pos, p) + nm(p, des.pos) <= direct * 1.3 + 80

        nodes = [n for n, p in nav.pos.items() if in_corridor(p)]
        allowed = set(nodes)

        def near(point, radius):
            return [n for n in nodes if nm(point, nav.pos[n]) <= radius]

        # 1 degree cells so direct legs only test nearby waypoints
        grid = defaultdict(list)

        def add_to_grid(node):
            p = nav.pos[node]
            grid[(math.floor(p[0]), math.floor(p[1]))].append(node)

        for n in nodes:
            add_to_grid(n)

        def direct_legs(node):
            p = nav.pos[node]
            dlat = math.ceil(DCT_RADIUS / 60)
            dlon = math.ceil(DCT_RADIUS / (60 * max(math.cos(math.radians(p[0])), 0.2)))
            cell_lat, cell_lon = math.floor(p[0]), math.floor(p[1])
            for i in range(cell_lat - dlat, cell_lat + dlat + 1):
                for j in range(cell_lon - dlon, cell_lon + dlon + 1):
                    for n in grid.get((i, j), ()):
                        d = nm(p, nav.pos[n])
                        if 0 < d <= DCT_RADIUS:
                            yield n, d * DCT_FACTOR, "DRCT"

        extra = defaultdict(list)  # node -> [(node, cost, label)]
        start = []  # (node, cost, sid option)
        sid_opts = dep.sid_options(dep_rwy) if dep_rwy else []
        threshold = dep.runways.get(dep_rwy, dep.pos)
        for opt in sid_opts:
            legs = opt[1] + opt[2]
            exit_node = nav.graph_node(*legs[-1])
            nav.pos.setdefault(exit_node, dep.fix_pos(legs[-1]))
            start.append((exit_node, dep.path_length(legs, threshold), opt))
        if not sid_opts:
            for n in near(dep.pos, 50):
                start.append((n, nm(dep.pos, nav.pos[n]), None))

        # Arrival: STAR entry node -> cost from entry to the runway
        finish = {}
        apps = des.approaches(des_rwy) if des_rwy else []
        if approach:
            apps = [a for a in apps if a[1] == approach]
            if not apps:
                raise ValueError(f"{des.icao} has no approach {approach} to {des_rwy}")
        app = apps[0] if apps else None
        app_entries = set(app[2]) - {""} if app else set()
        des_threshold = des.runways.get(des_rwy, des.pos)
        for opt in des.star_options(des_rwy) if des_rwy else []:
            legs = opt[1] + opt[2]
            entry = nav.graph_node(*legs[0])
            nav.pos.setdefault(entry, des.fix_pos(legs[0]))
            end = legs[-1]
            # A STAR that ends where an approach transition starts joins up cleanly
            link = 0 if end[0] in app_entries else 10 + nm(des.fix_pos(end), des_threshold)
            cost = des.path_length(legs) + link
            if entry not in finish or cost < finish[entry][0]:
                finish[entry] = (cost, opt)
            # Entries off the airway network are reached by direct legs
            if entry not in allowed:
                allowed.add(entry)
                add_to_grid(entry)
        if not finish:
            for n in near(des.pos, 50):
                finish[n] = (nm(nav.pos[n], des.pos), None)

        # Short hops: a SID end may go straight to a STAR entry
        for node, _, _ in start:
            for entry in finish:
                d = nm(nav.pos[node], nav.pos[entry])
                if d <= 80:
                    extra[node].append((entry, d * 1.1, "DRCT"))

        def search(cruise):
            """Cheapest route at this cruise level: (cost, goal state, states)."""

            # Airway segments are only usable where the profile altitude, climbing
            # from departure, cruising, then descending, sits inside their band
            def profile_altitude(p):
                return min(
                    cruise,
                    dep.elev + nm(dep.pos, p) * GRADIENT,
                    des.elev + nm(p, des.pos) * GRADIENT,
                )

            def airway_legs(node):
                p = nav.pos[node]
                for n, segs in nav.graph.get(node, {}).items():
                    if n not in allowed and n not in finish:
                        continue
                    q = nav.pos[n]
                    alt = profile_altitude(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
                    names = [name for name, base, top in segs if base <= alt <= top]
                    if names:
                        yield n, nm(p, q), "-".join(names)

            # Dijkstra from the SID exits to the STAR entries. A state is a
            # waypoint plus the airway flown into it, so switching airway can be
            # charged for.
            best = {}
            heap = []
            for i, (node, cost, opt) in enumerate(start):
                state = (node, None)
                if cost < best.get(state, (math.inf,))[0]:
                    best[state] = (cost, None, opt)
                    heapq.heappush(heap, (cost, i, state))
            counter = len(start)
            goal, goal_cost = None, math.inf
            while heap:
                cost, _, state = heapq.heappop(heap)
                if cost > best[state][0] or cost >= goal_cost:
                    continue
                node, airway = state
                if node in finish and cost + finish[node][0] < goal_cost:
                    goal, goal_cost = state, cost + finish[node][0]
                edges = (
                    list(airway_legs(node))
                    + extra.get(node, [])
                    + list(direct_legs(node))
                )
                for n, step, label in edges:
                    # Segments shared by several airways are named "A1-B2"
                    names = label.split("-")
                    next_airway = airway if airway in names else names[0]
                    if airway is not None and next_airway != airway:
                        step += AIRWAY_CHANGE
                    c = cost + step
                    next_state = (n, next_airway)
                    if c < best.get(next_state, (math.inf,))[0]:
                        best[next_state] = (c, state, None)
                        counter += 1
                        heapq.heappush(heap, (c, counter, next_state))
            return goal_cost, goal, best

        # Each allowed level opens different airways, keep the cheapest route
        levels = (
            [int(cruise_fl) * 100]
            if cruise_fl
            else cruise_levels(direct, course(dep.pos, des.pos))
        )
        results = []
        for level in levels:
            goal_cost, goal, best = search(level)
            if goal is not None:
                results.append((goal_cost, level, goal, best))
        if not results:
            raise RuntimeError(f"No route found {adep}-{ades}")
        _, cruise, goal, best = min(results, key=lambda r: r[0])

        # Walk back to the SID exit
        path = []
        state = goal
        while True:
            _, prev, opt = best[state]
            path.append(state)
            if prev is None:
                sid_opt = opt
                break
            state = prev
        path.reverse()
        star_opt = finish[goal[0]][1]

        return self._build(
            dep, des, dep_rwy, des_rwy, sid_opt, path, star_opt, app, cruise
        )

    def _build(self, dep, des, dep_rwy, des_rwy, sid_opt, path, star_opt, app, cruise):
        nav = self.nav
        # Enroute waypoints: SID transition, airways, STAR transition
        enroute = []
        if sid_opt:
            for leg in sid_opt[2][:-1]:
                enroute.append((leg[0], leg[2], "DRCT", dep.fix_pos(leg)))
        current = None
        for i, (node, label) in enumerate(path):
            if i == 0 and len(path) > 1 and sid_opt:
                # The SID ends here, the FMS flies it as part of the procedure
                if not sid_opt[2]:
                    continue
            if label and label != "DRCT":
                names = label.split("-")
                current = current if current in names else names[0]
                via = current
            else:
                via = "DRCT"
            enroute.append((node[0], node[2], via, nav.pos[node]))
        if star_opt:
            for leg in star_opt[1][1:]:
                enroute.append((leg[0], leg[2], "DRCT", des.fix_pos(leg)))
        # Drop repeats where procedure and airway meet
        dedup = []
        for wpt in enroute:
            if not dedup or dedup[-1][0] != wpt[0]:
                dedup.append(wpt)
        enroute = dedup

        # Distance along the whole flight for the altitude profile
        sid_pts = [dep.fix_pos(leg) for leg in sid_opt[1]] if sid_opt else []
        star_pts = [des.fix_pos(leg) for leg in star_opt[2]] if star_opt else []
        start_pt = dep.runways.get(dep_rwy, dep.pos)
        end_pt = des.runways.get(des_rwy, des.pos)
        chain = [start_pt] + sid_pts + [w[3] for w in enroute] + star_pts + [end_pt]
        along = [0.0]
        for a, b in zip(chain, chain[1:]):
            along.append(along[-1] + nm(a, b))
        total = along[-1]
        offset = 1 + len(sid_pts)

        lines = ["I", "1100 Version", f"CYCLE {nav.cycle}", f"ADEP {dep.icao}"]
        if dep_rwy:
            lines.append(f"DEPRWY {dep_rwy}")
        if sid_opt:
            lines.append(f"SID {sid_opt[0]}")
        lines.append(f"ADES {des.icao}")
        if des_rwy:
            lines.append(f"DESRWY {des_rwy}")
        if star_opt:
            lines.append(f"STAR {star_opt[0]}")
        if app:
            lines.append(f"APP {app[1]}")
        lines.append(f"NUMENR {len(enroute) + 2}")
        lines.append(f"1 {dep.icao} ADEP {dep.elev:.6f} {dep.lat:.6f} {dep.lon:.6f}")
        for i, (ident, kind, via, p) in enumerate(enroute):
            d = along[offset + i]
            alt = min(cruise, dep.elev + d * GRADIENT, des.elev + (total - d) * GRADIENT)
            lines.append(f"{kind} {ident} {via} {alt:.6f} {p[0]:.6f} {p[1]:.6f}")
        lines.append(f"1 {des.icao} ADES {des.elev:.6f} {des.lat:.6f} {des.lon:.6f}")

        summary = (
            f"{dep.icao} {dep_rwy or '-'} {sid_opt[0] if sid_opt else '-'} "
            f"{route_string(enroute)} {star_opt[0] if star_opt else '-'} "
            f"{app[1] if app else '-'} {des_rwy or '-'} {des.icao}, "
            f"{round(total)}nm FL{cruise // 100}"
        )
        return GeneratedPlan(dep.icao, des.icao, "\n".join(lines) + "\n", summary)

    def plan_path(self, adep, ades):
        return os.path.join(self._paths.fms_plans, f"{adep}-{ades}.fms")

    def plan_exists(self, adep, ades):
        return os.path.exists(self.plan_path(adep, ades))

    def write(self, plan: GeneratedPlan):
        """Save as ADEP-ADES.fms in the sim's plan folder; never overwrites."""
        path = self.plan_path(plan.adep, plan.ades)
        with open(path, "x") as f:
            f.write(plan.text)
        return path


def route_string(enroute):
    """Filed-route form: each airway followed by the fix it is flown to.

    The route starts at the SID's last fix, so a leading airway is flown from
    there and a leading direct leg needs no DCT.
    """
    tokens, prev_via = [], None
    for ident, _, via, _ in enroute:
        if tokens and via != "DRCT" and via == prev_via:
            tokens[-1] = ident
        elif via == "DRCT":
            tokens += (["DCT"] if tokens else []) + [ident]
        else:
            tokens += [via, ident]
        prev_via = via
    return " ".join(tokens)


def main():
    parser = argparse.ArgumentParser(
        description="Generate .fms flight plans from X-Plane's navdata",
        epilog="examples:\n"
        "  plan-gen EGCC-EHGG                    plan and save one route\n"
        "  plan-gen EGCC-EHGG --dep-rwy RW23R    pick the departure runway\n"
        "  plan-gen EGCC-EHGG --des-rwy RW23 --app R23\n"
        "                                        pick the arrival runway and approach\n"
        "  plan-gen --from EGCC                  destinations 1:00-1:30 away\n"
        "  plan-gen --from EGCC --min 45 --max 75\n\n"
        "Plans are saved to X-Plane's Output/FMS Plans as ADEP-ADES.fms and an\n"
        "existing plan is never overwritten. Runways not given are picked from\n"
        "the existing plans, then the prevailing wind (250).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("route", nargs="?", help="ADEP-ADES, e.g. EGCC-EHGG")
    parser.add_argument("--from", dest="origin", help="list destinations from ICAO")
    parser.add_argument("--min", type=int, default=60, help="minimum block minutes")
    parser.add_argument("--max", type=int, default=90, help="maximum block minutes")
    parser.add_argument("--dep-rwy", help="departure runway, e.g. RW23R")
    parser.add_argument("--des-rwy", help="arrival runway, e.g. RW05")
    parser.add_argument("--app", help="approach to --des-rwy, e.g. I05 or R05")
    parser.add_argument("--cruise", type=int, help="cruise level, e.g. 240")
    parser.add_argument(
        "--xplane-dir",
        default=DEFAULT_XPLANE_DIR,
        help=f"X-Plane install directory (default: {DEFAULT_XPLANE_DIR})",
    )
    args = parser.parse_args()
    if not args.route and not args.origin:
        parser.error("give a route or --from")

    download_missing()
    generator = Generator(XPlanePaths(os.path.expanduser(args.xplane_dir)))
    if args.origin:
        for d in generator.destinations(args.origin.upper(), args.min, args.max):
            mark = "*" if d.known else " "
            print(
                f"{mark} {d.iata:3} {d.city:24} ({d.icao}) "
                f"{d.distance:4.0f}nm {int(d.minutes) // 60}h{int(d.minutes) % 60:02d}"
            )
        return

    adep, ades = args.route.upper().split("-")
    # Checked up front so an existing plan does not cost a route search
    if generator.plan_exists(adep, ades):
        parser.exit(1, f"{generator.plan_path(adep, ades)} already exists\n")
    plan = generator.plan(
        adep, ades, args.dep_rwy, args.des_rwy, args.cruise, args.app
    )
    print(plan.summary)
    print(f"Saved {generator.write(plan)}")


if __name__ == "__main__":
    main()
