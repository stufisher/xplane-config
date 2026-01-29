from itertools import islice
import logging
import os
import time

from metar import Metar

logger = logging.getLogger(__name__)
DEFAULT_WEATHER_PATH = os.path.expanduser("~/X-Plane 12/Output/real weather")


def sorted_listing_by_creation_time(directory):
    def get_creation_time(item):
        item_path = os.path.join(directory, item)
        return os.path.getctime(item_path)

    items = os.listdir(directory)
    sorted_items = sorted(items, key=get_creation_time)
    return sorted_items


def get_lines_iterator(filename, n=3):
    with open(filename) as fp:
        for line in fp:
            yield [line] + list(islice(fp, n - 1))


class Weather:
    def __init__(self, path=None):
        self._path = path if path is not None else DEFAULT_WEATHER_PATH
        self._weather_cache = {}
        self._last_update = 0
        self._update_weather()

    def _update_weather(self):
        if time.time() - self._last_update < 60:
            return
        logger.info("Updating weather")
        metars = []
        for file in sorted_listing_by_creation_time(self._path):
            if file.startswith("metar"):
                metars.append(file)

        last = metars[-1]
        for lines in get_lines_iterator(os.path.join(self._path, last)):
            metar = lines[1].split(" ")
            self._weather_cache[metar[0]] = lines[1].strip()

        self._last_update = time.time()

    def get_forecast(self, airport: str):
        self._update_weather()
        try:
            metar_string = self._weather_cache[airport]
        except KeyError:
            logger.warning(f"Could not get weather for {airport}")
            return
        return Metar.Metar("METAR " + metar_string)


if __name__ == "__main__":
    weather = Weather()
    lsgg = weather.get_forecast("LSGG")
    print(lsgg)
