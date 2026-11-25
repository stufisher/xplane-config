from dataclasses import dataclass
from itertools import islice
import logging
import math
import os
import time

from metar import Metar

from .xplane import XPlanePaths

logger = logging.getLogger(__name__)


def sorted_listing_by_creation_time(directory):
    def get_creation_time(item):
        item_path = os.path.join(directory, item)
        return os.path.getmtime(item_path)

    items = os.listdir(directory)
    sorted_items = sorted(items)
    return sorted_items


def get_lines_iterator(filename, n=3):
    with open(filename) as fp:
        for line in fp:
            yield [line] + list(islice(fp, n - 1))


class Weather:
    def __init__(self, path=None):
        self._path = path if path is not None else XPlanePaths().real_weather
        self._weather_cache = {}
        self._last_update = 0
        self._update_weather()

    def _update_weather(self):
        if time.time() - self._last_update < 60:
            return
        logger.debug("Updating weather")
        metars = []
        for file in sorted_listing_by_creation_time(self._path):
            if file.startswith("metar"):
                metars.append(file)

        last = metars[-1]
        for lines in get_lines_iterator(os.path.join(self._path, last)):
            metar = lines[1].split(" ")
            self._weather_cache[metar[0]] = lines[1].strip()

        self._last_update = time.time()

    def stations(self):
        """ICAO codes of every station in the latest METAR file"""
        self._update_weather()
        return list(self._weather_cache)

    def get_forecast(self, airport: str):
        self._update_weather()
        try:
            metar_string = self._weather_cache[airport]
        except KeyError:
            logger.warning(f"Could not get weather for {airport}")
            return
        return Metar.Metar("METAR " + metar_string)


def metar_wind(metar):
    """(direction or None when variable, speed kt), None without a METAR"""
    if not metar or not metar.wind_speed:
        return None
    direction = metar.wind_dir.value() if metar.wind_dir else None
    return direction, metar.wind_speed.value("KT")


@dataclass
class Challenge:
    # Higher is harder; 0 is benign
    score: int
    # Short reasons, e.g. "X22 G35 V600 C300 TS"
    notes: str
    # The worst hazard as one symbol
    icon: str = "☀"


# Hazards from worst to mildest, each with its icon
HAZARD_ICONS = {
    "storm": "⛈",
    "frozen": "❄",
    "obscured": "🌫",
    "wind": "💨",
    "rain": "🌧",
}


def crosswind(wind_dir, wind_kt, runway_headings):
    """Smallest crosswind over the runways; variable wind counts in full"""
    if not runway_headings:
        return 0
    if wind_dir is None:
        return wind_kt
    return min(
        abs(wind_kt * math.sin(math.radians(wind_dir - heading)))
        for heading in runway_headings
    )


def challenge(metar, runway_headings) -> Challenge:
    """How hard the METAR makes an arrival on the best aligned runway.

    Without a METAR the score is -1, so unknown weather sorts below calm.
    """
    if not metar:
        return Challenge(-1, "no METAR", "❔")
    score, notes, hazards = 0, [], set()

    wind = metar_wind(metar)
    gust = metar.wind_gust.value("KT") if metar.wind_gust else 0
    if wind:
        cross = crosswind(wind[0], max(wind[1], gust), runway_headings)
        if cross >= 15:
            score += 3 if cross >= 25 else 2
            notes.append(f"X{cross:.0f}")
            hazards.add("wind")
    if gust >= 25:
        score += 3 if gust >= 35 else 2
        notes.append(f"G{gust:.0f}")
        hazards.add("wind")

    vis = metar.vis.value("M") if metar.vis else None
    if vis is not None and vis < 5000:
        score += 3 if vis < 800 else 2 if vis < 1500 else 1
        notes.append(f"V{vis:.0f}")
        if vis < 1500:
            hazards.add("obscured")

    # Ceiling is the lowest broken, overcast or vertical visibility layer
    ceilings = [
        height.value("FT")
        for cover, height, _ in metar.sky
        if cover in ("BKN", "OVC", "VV") and height is not None
    ]
    if ceilings and min(ceilings) < 1000:
        ceiling = min(ceilings)
        score += 3 if ceiling < 200 else 2 if ceiling < 500 else 1
        notes.append(f"C{ceiling:.0f}")
        if ceiling < 500:
            hazards.add("obscured")

    for intensity, descriptor, precip, obscuration, _ in metar.weather:
        precip = precip or ""
        if descriptor == "TS":
            score += 3
            notes.append("TS")
            hazards.add("storm")
        if descriptor == "FZ" or any(p in precip for p in ("SN", "SG", "PL", "GR")):
            score += 2
            notes.append(f"{descriptor or ''}{precip}" or "FZ")
            hazards.add("frozen")
        elif intensity == "+" and precip:
            score += 1
            notes.append(f"+{precip}")
            hazards.add("rain")
        elif precip:
            hazards.add("rain")
        if obscuration == "FG":
            score += 1
            notes.append("FG")
            hazards.add("obscured")
    icon = next((i for h, i in HAZARD_ICONS.items() if h in hazards), "☀")
    return Challenge(score, " ".join(dict.fromkeys(notes)), icon)


if __name__ == "__main__":
    weather = Weather()
    lsgg = weather.get_forecast("LSGG")
    print(lsgg)
