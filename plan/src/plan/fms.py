from dataclasses import dataclass
import os

from airports.airport_data import get_airport_by_icao

DEFAULT_FMS_PATH = os.path.expanduser("~/X-Plane 12/Output/FMS Plans")
DEFAULT_CIFP_PATH = os.path.expanduser("~/X-Plane 12/Resources/default dats/CIFP")


class CIFP:
    def __init__(self):
        pass

    def get_procedure(self, icao_code: str, procedure_name: str):
        file_path = os.path.join(DEFAULT_CIFP_PATH, f"{icao_code}.dat")
        with open(file_path) as cifp_file:
            for line in cifp_file:
                if procedure_name in line:
                    pass


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


@dataclass
class Waypoint:
    type_id: int
    name: str
    type: str
    latitude: float
    longitude: float
    altitude: float


class FMS:
    def __init__(self, path=None):
        self._path = path if path is not None else DEFAULT_FMS_PATH
        self._plans = {}
        self._update_plans()

    def _parse_plan(self, file_path: str):
        with open(file_path) as file:
            fms = {"waypoints": []}

            first = True
            in_waypoints = False
            for line in file:
                line = line.strip()
                if first:
                    first = False
                    continue
                if in_waypoints:
                    wpt = line.split(" ")
                    fms["waypoints"].append(
                        Waypoint(
                            type_id=wpt[0],
                            name=wpt[1],
                            type=wpt[2],
                            altitude=wpt[3],
                            latitude=wpt[4],
                            longitude=wpt[5],
                        )
                    )
                else:
                    key, value = line.split(" ")
                    fms[key] = value
                    if key == "NUMENR":
                        in_waypoints = True

            fms["departure"] = get_airport_by_icao(fms["ADEP"])[0]["airport"]
            fms["destination"] = get_airport_by_icao(fms["ADES"])[0]["airport"]
            return fms

    def _update_plans(self):
        self._plans = []
        for file_name in os.listdir(self._path):
            if file_name.endswith(".fms"):
                file_path = os.path.join(self._path, file_name)
                plan = self._parse_plan(file_path)
                self._plans.append(
                    {
                        "file_path": file_path,
                        "departure": plan["departure"],
                        "destination": plan["destination"],
                    }
                )

    @property
    def plans(self):
        self._update_plans()
        return self._plans

    def get_plan(self, file_path):
        return self._parse_plan(file_path)


if __name__ == "__main__":
    fms = FMS()

    coords = (45.435120, 6.687012)
    lat = decdeg2dms(coords[0])
    lon = decdeg2dms(coords[1])
    print(lat, lon)
    sp = latlon_to_fms(*coords)
    print(sp)
