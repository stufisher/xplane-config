"""Winds aloft from X-Plane's real weather GRIB2 file, or the same GFS data
fetched from NOAA NOMADS.

Only what that file uses is supported: a regular lat/lon grid (template 3.0)
with U and V wind on isobaric levels, complex packing with spatial
differencing (template 5.3) and no bitmap.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import glob
import logging
import math
import os
import struct
import time

import httpx

logger = logging.getLogger(__name__)

# GRIB2 meteorological parameters, discipline 0 category 2
U_WIND, V_WIND = 2, 3
# Level type of isobaric surfaces, in Pa
ISOBARIC = 100
MS_TO_KT = 1.943844

# GFS 1° wind as X-Plane's real weather downloads it, from NOMADS
NOMADS_URL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_1p00.pl"
NOMADS_LEVELS_MB = (100, 150, 200, 250, 300, 400, 500, 600, 700, 800, 900, 950)
# A run is published a few hours after its time; older runs are tried in turn
GFS_RUN_HOURS = 6
GFS_RUNS_TRIED = 4
# Forecasts are every 3 hours; the one valid nearest now is used
GFS_STEP_HOURS = 3
LIVE_WINDS_REFRESH_S = 1800
LIVE_WINDS_DIR = os.path.expanduser("~/.cache/plan/gfs")


def pressure_altitude_ft(hpa: float) -> float:
    return 145366.45 * (1 - (hpa / 1013.25) ** 0.190284)


def signed(value: int, bits: int) -> int:
    """GRIB2 stores negative numbers as sign and magnitude, not two's complement"""
    sign = 1 << (bits - 1)
    return -(value & (sign - 1)) if value & sign else value


class BitReader:
    def __init__(self, data: bytes, pos: int = 0):
        self._data = data
        self._bit = pos * 8

    def read(self, bits: int) -> int:
        if bits == 0:
            return 0
        start, end = self._bit, self._bit + bits
        chunk = int.from_bytes(self._data[start // 8 : (end + 7) // 8], "big")
        self._bit = end
        return (chunk >> (-end % 8)) & ((1 << bits) - 1)

    def read_many(self, count: int, bits: int) -> list:
        return [self.read(bits) for _ in range(count)]

    def align(self):
        self._bit = (self._bit + 7) // 8 * 8


@dataclass
class Grid:
    ni: int
    nj: int
    lat1: float
    lon1: float
    di: float
    dj: float
    # Rows run south from lat1 when True
    south: bool


@dataclass
class Message:
    parameter: int
    level_type: int
    level: int
    grid: Grid
    section5: bytes
    section7: bytes


def read_messages(path: str) -> list[Message]:
    """Headers of every message, with the packed data left undecoded"""
    data = open(path, "rb").read()
    messages = []
    pos = data.find(b"GRIB")
    while pos >= 0:
        total = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
        end = pos + total
        p = pos + 16
        grid = parameter = level_type = level = section5 = section7 = None
        while p < end - 4:
            length, number = struct.unpack(">IB", data[p : p + 5])
            body = data[p : p + length]
            if number == 3:
                ni, nj = struct.unpack(">II", body[30:38])
                lat1 = signed(struct.unpack(">I", body[46:50])[0], 32) / 1e6
                lon1 = signed(struct.unpack(">I", body[50:54])[0], 32) / 1e6
                di, dj = (v / 1e6 for v in struct.unpack(">II", body[63:71]))
                grid = Grid(ni, nj, lat1, lon1, di, dj, south=not body[71] & 0x40)
            elif number == 4:
                parameter = body[10]
                level_type = body[22]
                level = struct.unpack(">I", body[24:28])[0]
            elif number == 5:
                section5 = body
            elif number == 7:
                section7 = body
            p += length
        messages.append(
            Message(parameter, level_type, level, grid, section5, section7)
        )
        pos = data.find(b"GRIB", end)
    return messages


def unpack_complex(section5: bytes, section7: bytes, npoints: int) -> list[float]:
    """Values of a template 5.3 message: complex packing, spatial differencing"""
    reference = struct.unpack(">f", section5[11:15])[0]
    binary_scale = signed(struct.unpack(">H", section5[15:17])[0], 16)
    decimal_scale = signed(struct.unpack(">H", section5[17:19])[0], 16)
    nbits = section5[19]
    ngroups = struct.unpack(">I", section5[31:35])[0]
    width_reference = section5[35]
    width_bits = section5[36]
    length_reference = struct.unpack(">I", section5[37:41])[0]
    length_increment = section5[41]
    last_length = struct.unpack(">I", section5[42:46])[0]
    length_bits = section5[46]
    order = section5[47]
    extra_octets = section5[48]

    bits = BitReader(section7, 5)
    first_values = [
        signed(bits.read(extra_octets * 8), extra_octets * 8) for _ in range(order)
    ]
    overall_min = signed(bits.read(extra_octets * 8), extra_octets * 8)

    references = bits.read_many(ngroups, nbits)
    bits.align()
    widths = [w + width_reference for w in bits.read_many(ngroups, width_bits)]
    bits.align()
    lengths = [
        length_reference + n * length_increment
        for n in bits.read_many(ngroups, length_bits)
    ]
    lengths[-1] = last_length
    bits.align()

    values = []
    for reference_value, width, length in zip(references, widths, lengths):
        if width == 0:
            values.extend([reference_value] * length)
        else:
            values.extend(reference_value + v for v in bits.read_many(length, width))
    values = values[:npoints]

    # Undo the spatial differencing; the first values are stored separately
    for i, value in enumerate(first_values):
        values[i] = value
    if order == 1:
        for i in range(1, len(values)):
            values[i] = values[i] + overall_min + values[i - 1]
    elif order == 2:
        for i in range(2, len(values)):
            values[i] = values[i] + overall_min + 2 * values[i - 1] - values[i - 2]

    scale = 2.0**binary_scale
    divisor = 10.0**decimal_scale
    return [(reference + v * scale) / divisor for v in values]


class WindField:
    """U and V on one isobaric level, decoded on first use."""

    def __init__(self, u: Message, v: Message):
        self.grid = u.grid
        self._messages = (u, v)
        self._values = None

    def _decode(self):
        if self._values is None:
            npoints = self.grid.ni * self.grid.nj
            self._values = tuple(
                unpack_complex(m.section5, m.section7, npoints) for m in self._messages
            )
        return self._values

    def at(self, lat: float, lon: float) -> tuple[float, float]:
        """(u, v) in m/s, bilinear between the four surrounding grid points"""
        g = self.grid
        u_values, v_values = self._decode()
        y = (g.lat1 - lat) / g.dj if g.south else (lat - g.lat1) / g.dj
        x = ((lon - g.lon1) % 360) / g.di
        j0 = min(max(int(math.floor(y)), 0), g.nj - 2)
        i0 = int(math.floor(x)) % g.ni
        i1 = (i0 + 1) % g.ni
        fy = min(max(y - j0, 0.0), 1.0)
        fx = x - math.floor(x)

        def blend(values):
            row0 = j0 * g.ni
            row1 = row0 + g.ni
            top = values[row0 + i0] * (1 - fx) + values[row0 + i1] * fx
            bottom = values[row1 + i0] * (1 - fx) + values[row1 + i1] * fx
            return top * (1 - fy) + bottom * fy

        return blend(u_values), blend(v_values)


class WindsAloft:
    """Wind at any position and altitude from a real weather GRIB2 file."""

    def __init__(self, path: str):
        self.path = path
        messages = read_messages(path)
        by_level = {}
        for m in messages:
            if m.level_type == ISOBARIC and m.parameter in (U_WIND, V_WIND):
                by_level.setdefault(m.level, {})[m.parameter] = m
        # Lowest altitude first: altitude in ft against the level's field
        self._levels = sorted(
            (pressure_altitude_ft(level / 100), WindField(pair[U_WIND], pair[V_WIND]))
            for level, pair in by_level.items()
            if U_WIND in pair and V_WIND in pair
        )

    def wind(self, lat: float, lon: float, altitude_ft: float) -> tuple[float, float]:
        """(direction the wind blows from in degrees, speed kt)"""
        levels = self._levels
        if altitude_ft <= levels[0][0]:
            u, v = levels[0][1].at(lat, lon)
        elif altitude_ft >= levels[-1][0]:
            u, v = levels[-1][1].at(lat, lon)
        else:
            for (alt0, field0), (alt1, field1) in zip(levels, levels[1:]):
                if alt0 <= altitude_ft <= alt1:
                    f = (altitude_ft - alt0) / (alt1 - alt0)
                    u0, v0 = field0.at(lat, lon)
                    u1, v1 = field1.at(lat, lon)
                    u, v = u0 + (u1 - u0) * f, v0 + (v1 - v0) * f
                    break
        speed = math.hypot(u, v) * MS_TO_KT
        direction = (math.degrees(math.atan2(-u, -v)) + 360) % 360
        return direction, speed


class LiveWinds:
    """GFS winds from NOMADS for the forecast time nearest now, from the newest
    run published. refresh() downloads and is slow, so it runs off the UI
    thread; winds holds the last one fetched."""

    def __init__(self, directory: str = LIVE_WINDS_DIR):
        self._directory = directory
        self.winds: WindsAloft | None = None
        self._last_update = 0

    def refresh(self, force: bool = False):
        """Fetch winds once they are LIVE_WINDS_REFRESH_S old, or now"""
        if not force and time.time() - self._last_update < LIVE_WINDS_REFRESH_S:
            return
        self._last_update = time.time()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        step = timedelta(hours=GFS_STEP_HOURS)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        valid = midnight + round((now - midnight) / step) * step
        run = midnight + timedelta(hours=now.hour // GFS_RUN_HOURS * GFS_RUN_HOURS)
        for _ in range(GFS_RUNS_TRIED):
            path = self._fetch(run, int((valid - run).total_seconds() // 3600))
            if path:
                if self.winds is None or self.winds.path != path:
                    try:
                        self.winds = WindsAloft(path)
                    except (OSError, ValueError, IndexError, struct.error):
                        logger.warning(f"Could not read live winds from {path}")
                        os.remove(path)
                        return
                    logger.info(f"Live winds from {os.path.basename(path)}")
                    self._remove_others(path)
                return
            run -= timedelta(hours=GFS_RUN_HOURS)
        logger.warning("Could not fetch live winds")

    def _fetch(self, run: datetime, hour: int) -> str | None:
        """Path of the run's forecast for hour, downloaded unless already
        cached; None when NOMADS does not have it yet"""
        path = os.path.join(self._directory, f"gfs-{run:%Y%m%d-%H}z-f{hour:03d}.grib")
        if os.path.exists(path):
            return path
        params = {
            "dir": f"/gfs.{run:%Y%m%d}/{run:%H}/atmos",
            "file": f"gfs.t{run:%H}z.pgrb2.1p00.f{hour:03d}",
            "var_UGRD": "on",
            "var_VGRD": "on",
            "lev_10_m_above_ground": "on",
            **{f"lev_{level}_mb": "on" for level in NOMADS_LEVELS_MB},
        }
        try:
            response = httpx.get(NOMADS_URL, params=params, timeout=60)
        except httpx.HTTPError as e:
            logger.warning(f"Could not fetch live winds: {e}")
            return None
        # A run not yet published answers 404 with an HTML page
        if response.status_code != 200 or not response.content.startswith(b"GRIB"):
            logger.debug(f"No GFS {run:%Y%m%d %H}z f{hour:03d} yet")
            return None
        os.makedirs(self._directory, exist_ok=True)
        # Written aside then renamed, so a partial file is never read
        partial = path + ".part"
        with open(partial, "wb") as file:
            file.write(response.content)
        os.replace(partial, path)
        return path

    def _remove_others(self, keep: str):
        for path in glob.glob(os.path.join(self._directory, "gfs-*.grib")):
            if path != keep:
                try:
                    os.remove(path)
                except OSError:
                    logger.debug(f"Could not remove {path}")


def latest_grib(directory: str):
    """Newest wind GRIB in X-Plane's real weather folder, None when absent"""
    files = sorted(glob.glob(os.path.join(directory, "GRIB-*wind*.grib")))
    return files[-1] if files else None
