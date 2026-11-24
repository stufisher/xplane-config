import csv
from dataclasses import dataclass
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# OpenFlights lists the city each airport serves, as a departure board shows it
OPENFLIGHTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)
DEFAULT_PATH = os.path.expanduser("~/.cache/plan/openflights_airports.dat")


def download_missing(path: str = DEFAULT_PATH):
    """Fetch the OpenFlights airports file if not present; failures are logged, not raised"""
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    logger.info(f"Downloading {OPENFLIGHTS_URL} to {path}")
    try:
        response = httpx.get(OPENFLIGHTS_URL, follow_redirects=True, timeout=60)
        response.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning(f"Could not download {OPENFLIGHTS_URL}: {e}")
        return
    # Write then rename so an interrupted download never leaves a partial file
    with open(path + ".part", "wb") as file:
        file.write(response.content)
    os.replace(path + ".part", path)


@dataclass
class Place:
    city: Optional[str]
    iata: Optional[str]


class Places:
    """City served and IATA code of each airport, as on a departure board"""

    def __init__(self, path: str = DEFAULT_PATH):
        self._path = path
        self._loaded = False
        self._places: dict[str, Place] = {}

    def _load(self):
        self._loaded = True
        try:
            with open(self._path, encoding="utf-8") as file:
                # id, name, city, country, IATA, ICAO, ...; \N marks a missing value
                for row in csv.reader(file):
                    if len(row) > 5 and row[5] != "\\N":
                        iata = row[4] if row[4] != "\\N" else None
                        self._places[row[5]] = Place(row[2] or None, iata)
        except OSError as e:
            logger.warning(f"OpenFlights data unavailable: {e}")

    def lookup(self, icao_code: str) -> Place:
        """City and IATA code from OpenFlights, each None when unknown"""
        if not self._loaded:
            self._load()
        return self._places.get(icao_code, Place(None, None))
