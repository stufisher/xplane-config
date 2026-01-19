import asyncio
from dataclasses import dataclass
import logging

from .fms import FMS
from .rest import REST
from .weather import Weather

logger = logging.getLogger(__name__)


@dataclass
class Location:
    latitude: float
    longitude: float
    elevation: float
    theta: float
    phi: float
    psi: float


class Plan:
    def __init__(self):
        self._fms = FMS()
        self._rest = REST()
        self._weather = Weather()
        self._plan = None

    async def _init(self):
        await self._rest._init()

    def load_plan(self, file_path: str):
        self._plan = self._fms.get_plan(file_path)

    @property
    def current(self):
        return self._plan

    @property
    def cruise(self):
        if not self._plan:
            return

        max_alt = 0
        for waypoint in self._plan["waypoints"]:
            wpt_alt = float(waypoint.altitude)
            if wpt_alt > max_alt:
                max_alt = wpt_alt

        return int(max_alt / 100)

    @property
    def plans(self):
        return self._fms.plans

    @property
    def weather_des(self):
        if not self._plan:
            return
        return self._weather.get_forecast(self._plan["ADES"])

    @property
    def weather_dep(self):
        if not self._plan:
            return
        return self._weather.get_forecast(self._plan["ADEP"])

    async def mcdu_init(self, cost=10, flt_number="A123", cruise_alt=350):
        await self._rest.press_button("INIT")
        await self._rest.write_scratchpad(self._plan["ADEP"] + "/" + self._plan["ADES"])
        await self._rest.press_button("1R")
        await self._rest.press_button("6R")

        # Misc
        await self._rest.write_scratchpad(flt_number)
        await self._rest.press_button("3L")
        await self._rest.write_scratchpad(str(cost))
        await self._rest.press_button("5L")
        await self._rest.write_scratchpad(str(cruise_alt))
        await self._rest.press_button("6L")

        # IRS Init
        await self._rest.press_button("3R")
        await self._rest.press_button("6L")

        # Wind Req
        await self._rest.press_button("4R")
        await self._rest.press_button("3R")
        await self._rest.press_button("6L")

        # Setup dep
        await self._rest.press_button("FPLN")
        await self._rest.press_button("1L")
        await asyncio.sleep(0.2)
        await self._rest.press_button("1L")
        dep_runway = self._plan["DEPRWY"].replace("RW", "")
        row_id = await self._rest.find_row_in_display(dep_runway)
        if row_id is not None:
            await self._rest.press_button(f"{row_id+1}L")
        else:
            logger.warning(f"Could not set departure runway `{dep_runway}`")

        sid = self._plan["SID"]
        row_id = await self._rest.find_row_in_display(sid)
        if row_id is not None:
            await self._rest.press_button(f"{row_id+1}L")
        else:
            logger.warning(f"Could not set departure SID `{sid}`")

        await self._rest.press_button("2R")
        await self._rest.press_button("6R")

        # Setup dest
        await self._rest.press_button("6L")
        await self._rest.press_button("1R")

        # Approach
        app = self._plan["APP"]
        if app.startswith("L"):
            app = app.replace("L", "LOC")
        if app.startswith("I"):
            app = app.replace("I", "ILS")
        if app.startswith("R"):
            app = app.replace("R", "RNV")
        row_id = await self._rest.find_row_in_display(app)
        if row_id is not None:
            await self._rest.press_button(f"{row_id+1}L")
        else:
            logger.warning(f"Could not set departure APP `{app}`")

        # Star
        star = self._plan.get("STAR")
        if star:
            row_id = await self._rest.find_row_in_display(star)
            if row_id is not None:
                await self._rest.press_button(f"{row_id+1}L")
            else:
                logger.warning(f"Could not set departure STAR `{star}`")
        else:
            logger.info("No STAR")

        await asyncio.sleep(0.2)
        await self._rest.press_button("6R")

        # Tidy default discontinuity
        row_id = await self._rest.find_row_in_display(
            "DISCON", color="w", secondary="g"
        )
        if row_id is not None:
            manual_id = await self._rest.find_row_in_display(
                "MANUAL", color="g", iterate=False
            )
            if manual_id is None:
                logger.info("Removing discontinuity")
                await self._rest.press_button("CLR")
                await self._rest.press_button(f"{row_id+1}L")
                await self._rest.press_button("6R")
            else:
                logger.info("Not removing discontinuity, part of manual")

    async def mcdu_perf(self, to_flaps="1/UP0.0", flex=73):
        await self._rest.press_button("PERF")
        await self._rest.write_scratchpad(to_flaps)
        await self._rest.press_button("3R")
        await self._rest.write_scratchpad(str(flex))
        await self._rest.press_button("4R")

        await self._rest.set_dataref("toliss_airbus/performance/VR", 145)
        await self._rest.set_dataref("toliss_airbus/performance/V1", 145)
        await self._rest.set_dataref("toliss_airbus/performance/V2", 155)

    async def mcdu_fpln(self):
        await self._rest.press_button("FPLN")

    @property
    async def location(self):
        latitude = await self._rest.get_dataref("sim/flightmodel/position/latitude")
        longitude = await self._rest.get_dataref("sim/flightmodel/position/longitude")
        elevation = await self._rest.get_dataref("sim/flightmodel/position/elevation")

        theta = await self._rest.get_dataref("sim/flightmodel/position/theta")
        phi = await self._rest.get_dataref("sim/flightmodel/position/phi")
        psi = await self._rest.get_dataref("sim/flightmodel/position/psi")

        return Location(
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            theta=theta,
            phi=phi,
            psi=psi,
        )

    async def shutdown(self):
        logger.info("Plan: Shutdown")
        await self._rest.shutdown()


def run():
    plan = Plan()
    # plan.load_plan("/Users/clementine/X-Plane 12/Output/FMS Plans/LFLL-LOWI.fms")
    # plan.load_plan("/Users/clementine/X-Plane 12/Output/FMS Plans/LFLL-LSZH.fms")
    plan.load_plan("/Users/clementine/X-Plane 12/Output/FMS Plans/LFPO-EGLC.fms")
    print(plan.weather_des.string())
    # plan.mcdu_init()
    # plan.mcdu_perf()
    print(plan.location)


if __name__ == "__main__":
    run()
