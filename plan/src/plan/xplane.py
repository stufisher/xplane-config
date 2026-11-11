from dataclasses import dataclass
import os

DEFAULT_XPLANE_DIR = os.path.expanduser("~/X-Plane 12")


@dataclass(frozen=True)
class XPlanePaths:
    """Locations of the data files inside an X-Plane install"""

    root: str = DEFAULT_XPLANE_DIR

    def _join(self, *parts: str):
        return os.path.join(self.root, *parts)

    @property
    def fms_plans(self):
        return self._join("Output", "FMS Plans")

    @property
    def real_weather(self):
        return self._join("Output", "real weather")

    @property
    def cifp(self):
        return self._join("Resources", "default data", "CIFP")

    @property
    def earth_fix(self):
        return self._join("Resources", "default data", "earth_fix.dat")

    @property
    def earth_nav(self):
        return self._join("Resources", "default data", "earth_nav.dat")

    @property
    def apt(self):
        return self._join(
            "Global Scenery", "Global Airports", "Earth nav data", "apt.dat"
        )
