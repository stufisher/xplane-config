import asyncio
from dataclasses import dataclass
import logging

from nicegui import background_tasks, run as ng_run

from .apt import APT
from .fms import FMS
from .rest import REST
from .weather import Weather
from .to.to import TOCalculator

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
    def __init__(
        self, apt: APT, update_time: callable = None, update_location: callable = None
    ):
        self._fms = FMS(apt)
        self._rest = REST(on_drefs_changed=self.on_drefs_changed)
        self._weather = Weather()
        self._plan = None
        self._to = TOCalculator(self._rest, apt, self._weather)

        self._time_dref = "sim/time/zulu_time_sec,0"
        self._location_drefs = [
            "sim/flightmodel/position/latitude,3",
            "sim/flightmodel/position/longitude,3",
            "sim/flightmodel/position/elevation,1",
            "sim/flightmodel/position/theta,1",
            "sim/flightmodel/position/phi,1",
            "sim/flightmodel/position/psi,1",
        ]
        self._update_time = update_time
        self._update_location = update_location

    def on_drefs_changed(self, drefs: dict[str, any]):
        for dref in drefs:
            if dref == self._time_dref:
                if self._update_time:
                    self._update_time()

            if dref in self._location_drefs:
                if self._update_location:
                    self._update_location()

    async def _init(self):
        await self._rest._init()
        self._rest.set_subscribed_drefs(self._location_drefs + [self._time_dref])
        background_tasks.create(self._rest.socket_client())

    async def load_plan(self, file_path: str, load_runway=False):
        self._plan = await self._fms.get_plan(file_path, load_runway)

    @property
    def current(self):
        return self._plan

    @property
    def cruise(self):
        if not self._plan:
            return

        max_alt = 0
        for waypoint in self._plan.waypoints:
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
        return self._weather.get_forecast(self._plan.ADES)

    @property
    def weather_dep(self):
        if not self._plan:
            return
        return self._weather.get_forecast(self._plan.ADEP)

    async def mcdu_init(self, cost=10, flt_number="A123", cruise_alt=350):
        logger.info("MCDU: Init")
        await self._rest.press_button("INIT")
        await self._rest.write_scratchpad(self._plan.ADEP + "/" + self._plan.ADES)
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
        logger.info("MCDU: IRS Init")
        await self._rest.press_button("3R")
        await self._rest.press_button("6L")

        # Wind Req
        logger.info("MCDU: Wind request")
        await self._rest.press_button("4R")
        await self._rest.press_button("3R")
        await self._rest.press_button("6L")

        # Setup dep
        await self._rest.press_button("FPLN")
        await self._rest.press_button("1L")
        await asyncio.sleep(0.2)
        await self._rest.press_button("1L")
        dep_runway = self._plan.DEPRWY.replace("RW", "")
        logger.info(f"MCDU: Setting departure runway {dep_runway}")
        row_id = await self._rest.find_row_in_display(dep_runway)
        if row_id is not None:
            await self._rest.press_button(f"{row_id+1}L")
        else:
            logger.warning(f"Could not set departure runway `{dep_runway}`")

        sid = self._plan.SID
        if sid is None:
            sid = "NO SID"
        logger.info(f"MCDU: Setting departure SID {sid}")
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
        des_runway = self._plan.DESRWY.replace("RW", "RWY")
        app = self._plan.APP
        if app:
            logger.info(f"MCDU: Setting arrival approach {app}")
            if app.startswith("L"):
                app = app.replace("L", "LOC")
            if app.startswith("I"):
                app = app.replace("I", "ILS")
            if app.startswith("G"):
                app = app.replace("G", "IGS")
            if app.startswith("R"):
                app = app.replace("R", "RNV")
            row_id = await self._rest.find_row_in_display(app)
            if row_id is not None:
                await self._rest.press_button(f"{row_id+1}L")
            else:
                # Try dashed variant
                if (
                    app.endswith("X") or app.endswith("Y") or app.endswith("Z")
                ) and "-" not in app:
                    app = app[:-1] + "-" + app[-1]
                    logger.info(f"MCDU: Trying dashed variant of APP `{app}`")
                    row_id = await self._rest.find_row_in_display(app, direction="DOWN")
                    if row_id is not None:
                        await self._rest.press_button(f"{row_id+1}L")
                    else:
                        logger.warning(f"Could not set departure APP `{app}`")
                else:
                    logger.warning(f"Could not set departure APP `{app}`")

            # Star
            star = self._plan.STAR
            if star:
                logger.info(f"MCDU: Setting arrival STAR {star}")
                row_id = await self._rest.find_row_in_display(star)
                if row_id is not None:
                    await self._rest.press_button(f"{row_id+1}L")
                else:
                    logger.warning(f"Could not set departure STAR `{star}`")
            else:
                logger.info("No STAR")

        # No procedures but we do have a destination runway
        elif des_runway:
            logger.info(f"MCDU: No procedures, setting dest runway {des_runway}")
            if row_id is not None:
                await self._rest.press_button(f"{row_id+1}L")
            # Set no STAR
            row_id = await self._rest.find_row_in_display("NO STAR")
            if row_id is not None:
                await self._rest.press_button(f"{row_id+1}L")

        else:
            logger.warning("MCDU: No Desintation")

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
                logger.info("MCDU: Removing discontinuity")
                await self._rest.press_button("CLR")
                await self._rest.press_button(f"{row_id+1}L")
                await self._rest.press_button("6R")
            else:
                logger.info("Not removing discontinuity, part of manual")

    async def mcdu_perf(
        self, to_flaps="1", runway_condition=0, packs=True, anti_ice=False
    ):
        logger.info("MCDU: Setting PERF")
        trim = await self._to.calc_trim()
        dep_runway = self._plan.DEPRWY.replace("RW", "")
        flex_vspeeds = await self._to.calc_vspeeds_flex(
            self._plan.ADEP, dep_runway, to_flaps, runway_condition, packs, anti_ice
        )
        if flex_vspeeds.invalid:
            logger.error(
                f"TO Invalid, required runway {flex_vspeeds.requiredRunway} > {flex_vspeeds.availRunway}"
            )
            return
        log_type = logger.info if flex_vspeeds.flex else logger.warning
        log_type(
            f"TO Params: V1 {flex_vspeeds.v1} VR {flex_vspeeds.vr} V2 {flex_vspeeds.v2} Flex Temp: {flex_vspeeds.flex} Trim {trim}"
        )
        if not flex_vspeeds.flex:
            logger.info(
                f"TO Params: Required runway {flex_vspeeds.requiredRunway}ft (available {flex_vspeeds.availRunway}ft)"
            )
        await self._rest.press_button("PERF")
        await self._rest.write_scratchpad(f"{to_flaps}/{trim}")
        await self._rest.press_button("3R")
        if flex_vspeeds.flex:
            await self._rest.write_scratchpad(str(flex_vspeeds.flex))
            await self._rest.press_button("4R")

        await self._rest.set_dataref("toliss_airbus/performance/VR", flex_vspeeds.vr)
        await self._rest.set_dataref("toliss_airbus/performance/V1", flex_vspeeds.v1)
        await self._rest.set_dataref("toliss_airbus/performance/V2", flex_vspeeds.v2)

    async def mcdu_fpln(self):
        await self._rest.press_button("FPLN")

    @property
    def time(self):
        seconds = self._rest.get_dref_value("sim/time/zulu_time_sec,0")
        return seconds

    @property
    def location(self):
        latitude = self._rest.get_dref_value("sim/flightmodel/position/latitude,3")
        longitude = self._rest.get_dref_value("sim/flightmodel/position/longitude,3")
        elevation = self._rest.get_dref_value("sim/flightmodel/position/elevation,1")

        theta = self._rest.get_dref_value("sim/flightmodel/position/theta,1")
        phi = self._rest.get_dref_value("sim/flightmodel/position/phi,1")
        psi = self._rest.get_dref_value("sim/flightmodel/position/psi,1")

        return Location(
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            theta=theta or 0,
            phi=phi or 0,
            psi=psi or 0,
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
