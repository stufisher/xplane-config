import asyncio
from dataclasses import dataclass
import logging

from nicegui import background_tasks, run as ng_run

from .apt import APT
from .fms import FMS
from .rest import REST
from .weather import Weather
from .xplane import XPlanePaths
from .to.to import FlexVSpeeds, TOCalculator

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
        self,
        apt: APT,
        update_time: callable = None,
        update_location: callable = None,
        paths: XPlanePaths = XPlanePaths(),
    ):
        self._fms = FMS(apt, paths)
        self._rest = REST(on_drefs_changed=self.on_drefs_changed)
        self._weather = Weather(paths.real_weather)
        self._plan = None
        self._to = TOCalculator(self._rest, apt, self._weather)
        # Latest takeoff calculation, None until PERF has been calculated
        self.takeoff: FlexVSpeeds | None = None

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

    async def load_plan(self, file_path: str):
        self._plan = await self._fms.get_plan(file_path)

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

    def forecast(self, icao: str):
        """Latest METAR for any airport, None when the sim has none"""
        return self._weather.get_forecast(icao)

    def metar_stations(self):
        """ICAO codes the sim has METARs for"""
        return self._weather.stations()

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

        # The first TRANS entry, at 2R, is NO TRANS
        if not (
            self._plan.SIDTRANS
            and await self._select_transition(self._plan.SIDTRANS, "SID")
        ):
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
            # Only a type letter in front of a runway is spelt out, e.g.
            # R24RY -> RNV24RY; circling names such as LOCA stay as they are
            prefixes = {"L": "LOC", "I": "ILS", "G": "IGS", "R": "RNV"}
            if app[:1] in prefixes and app[1:2].isdigit():
                app = prefixes[app[0]] + app[1:]
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
                    await self._select_via_and_transition()
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

    async def _select_via_and_transition(self):
        """After the STAR the ARRIVAL page offers the approach vias on the left,
        then the STAR transitions on the right"""
        # NO VIA is the first entry, at 3L
        if not (self._plan.APPTRANS and await self._select_via(self._plan.APPTRANS)):
            await self._rest.press_button("3L")
        # NO TRANS is the first entry, at 3R
        if not (
            self._plan.STARTRANS
            and await self._select_transition(self._plan.STARTRANS, "STAR")
        ):
            await self._rest.press_button("3R")

    async def _select_transition(self, transition: str, kind: str) -> bool:
        """Pick a SID or STAR enroute transition from the TRANS column on the right"""
        logger.info(f"MCDU: Setting {kind} transition {transition}")
        row_id = await self._rest.find_row_in_display(transition, side="R")
        if row_id is None:
            logger.warning(f"Could not set {kind} transition `{transition}`")
            return False
        await self._rest.press_button(f"{row_id+1}R")
        return True

    async def _select_via(self, via: str) -> bool:
        """Pick the approach transition from the VIA list on the left"""
        logger.info(f"MCDU: Setting approach via {via}")
        row_id = await self._rest.find_row_in_display(via, side="L")
        if row_id is None:
            logger.warning(f"Could not set approach via `{via}`")
            return False
        await self._rest.press_button(f"{row_id+1}L")
        return True

    async def mcdu_perf(
        self, to_flaps="1", runway_condition=0, packs=True, anti_ice=False
    ):
        logger.info("MCDU: Setting PERF")
        self.takeoff = None
        trim, cg_out_of_range = await self._to.calc_trim()
        if cg_out_of_range:
            logger.error(f"TO Invalid, CG outside the trim chart (trim {trim})")
            return
        dep_runway = self._plan.DEPRWY.replace("RW", "")
        flex_vspeeds = await self._to.calc_vspeeds_flex(
            self._plan.ADEP, dep_runway, to_flaps, runway_condition, packs, anti_ice
        )
        if flex_vspeeds is None:
            return
        flex_vspeeds.trim = trim
        self.takeoff = flex_vspeeds
        if flex_vspeeds.invalid:
            if flex_vspeeds.v1 == -1:
                logger.error(
                    "TO Invalid, no V1 of 100kts or more allows a stop on the runway even with TOGA"
                )
            else:
                logger.error(
                    f"TO Invalid, required runway {flex_vspeeds.requiredRunway}ft > {flex_vspeeds.availRunway}ft"
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

        # V1, VR and V2 sit on the left of the PERF TAKE OFF page
        for lsk, speed in (
            ("1L", flex_vspeeds.v1),
            ("2L", flex_vspeeds.vr),
            ("3L", flex_vspeeds.v2),
        ):
            await self._rest.write_scratchpad(str(speed))
            await self._rest.press_button(lsk)

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
