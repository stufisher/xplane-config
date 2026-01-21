from dataclasses import dataclass
import os

DEFAULT_APD_PATH = os.path.expanduser(
    "~/X-Plane 12/Global Scenery/Global Airports/Earth nav data/apt.dat"
)

print(DEFAULT_APD_PATH)

TEST_DATA = """
1    21 1 0 KBFI Boeing Field King Co Intl
100  29.87   1   0 0.15 0 2 1 13L  47.53801700 -122.30746100   73.15    0.00 2  0 0 1 31R  47.52919200 -122.30000000  110.95    0.00 2  0 0 1
100  29.87   1   0 0.15 0 2 1 25L  46.53801700 -122.30746100   73.15    0.00 2  0 0 1 52R  46.52919200 -122.30000000  110.95    0.00 2  0 0 1
100  29.87   1   0 0.15 0 2 1 06  49.53801700 -102.30746100   73.15    0.00 2  0 0 1
101 49 1 08 35.04420900 -106.59855700 26 35.04420911 -106.59855711
102  H1   47.53918248 -122.30722302   2.00   10.06   10.06   1 0   0 0.25 0
21   47.53666659 -122.30585255  2 150.28   3.30 13L PAPI-2L
110  1 0.25 150.29 A2 Exit
111  47.53770968 -122.30849802
111  47.53742819 -122.30825844   3
"""


@dataclass
class Runway:
    name: str
    rwy_idx: int
    rwy_dir: int
    lat: float
    lon: float


class APT:
    def __init__(self):
        self._airports: dict[str, dict[str, Runway]] = {}

    def _parse(self, icao_code: str):
        runways = {}
        rw_idx = 0
        in_airport = False
        with open(DEFAULT_APD_PATH) as apd_file:
            for line in apd_file:
                parts = line.strip().split()
                if not parts:
                    continue
                if parts[0] == "1":
                    if in_airport:
                        in_airport = False
                    if parts[4] == icao_code:
                        in_airport = True

                if line.startswith("100") and in_airport:
                    fields = line.strip().split()
                    header = fields[0:8]
                    rws = fields[8:]
                    rw_count = int(len(rws) / 9)
                    for rw_dir in range(rw_count):
                        rw_fields = rws[rw_dir * 9 : rw_dir * 9 + 9]
                        runways[rw_fields[0]] = Runway(
                            name=rw_fields[0],
                            rwy_idx=rw_idx,
                            rwy_dir=rw_dir,
                            lat=float(rw_fields[1]),
                            lon=float(rw_fields[2]),
                        )

                    rw_idx += 1

            self._airports[icao_code] = runways

    def get_runway_idx_dir(self, icao_code: str, name: str):
        if icao_code not in self._airports:
            self._parse(icao_code)
        runways = self._airports[icao_code]
        if "RW" in name:
            name = name.replace("RW", "")
        return runways[name]


if __name__ == "__main__":
    apt = APT()
    print(apt.get_runway_idx_dir("LFLL", "35L"))
