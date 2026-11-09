# https://github.com/jbud/Flex-Calculator-TS/pull/14
# https://developer.x-plane.com/article/airport-data-apt-dat-12-00-file-format-specification/
# https://github.com/jbud/Flex-Calculator-TS/blob/master/src/airframes/a20n.ts
import asyncio
from dataclasses import dataclass
import logging

from nicegui import run as ng_run

from ..rest import REST
from ..apt import APT
from ..weather import Weather
from .flex import FlexMath, calculate_trim, TakeoffInstance, VSpeeds
from .airframe import a20n

logger = logging.getLogger(__name__)


@dataclass
class FlexVSpeeds(VSpeeds):
    flex: int | None
    requiredRunway: int
    availRunway: int
    invalid: bool
    icao: str
    runwayName: str
    runwayHeading: int
    windHeading: float
    windKts: float
    windVariable: bool
    # Pitch trim for the MCDU, filled in by the caller
    trim: str | None = None


class TOCalculator:
    def __init__(self, rest: REST, apt: APT, weather: Weather):
        self._rest = rest
        self._apt = apt
        self._weather = weather

    async def get_weight_cg(self):
        # value = await rest.get_dataref("sim/flightmodel2/misc/cg_offset_z")
        weight = await self._rest.get_dataref("sim/flightmodel/weight/m_total")
        cg_percent = await self._rest.get_dataref(
            "sim/flightmodel2/misc/cg_offset_z_mac"
        )
        return weight, cg_percent

    async def calc_trim(self):
        cg_percent = await self._rest.get_dataref(
            "sim/flightmodel2/misc/cg_offset_z_mac"
        )
        return calculate_trim(cg_percent)

    async def calc_vspeeds_flex(
        self,
        icao_code: str,
        runway_name: str,
        flaps: int,
        runway_condition: int,
        packs: bool = True,
        anti_ice: bool = False,
    ):
        weight = await self._rest.get_dataref("sim/flightmodel/weight/m_total")
        current_weather = self._weather.get_forecast(icao_code)
        runway = await self._apt.get_runway_heading_and_length(icao_code, runway_name)

        if runway is None:
            logger.error(f"No runway data for {icao_code} {runway_name}")
            return None
        if (
            current_weather is None
            or current_weather.press is None
            or current_weather.temp is None
        ):
            logger.error(f"No QNH or temperature in METAR for {icao_code}")
            return None

        # VRB wind has no direction, so its speed is applied from 000
        wind_dir = current_weather.wind_dir
        wind_heading = wind_dir.value() if wind_dir is not None else 0
        speed = current_weather.wind_speed
        wind_speed = speed.value("KT") if speed is not None else 0

        settings = TakeoffInstance(
            **{
                "availRunway": runway.length * 3.28084,
                # FlexMath multiplies by 10, expecting a runway number
                "runwayHeading": runway.heading / 10,
                "runwayAltitude": runway.elevation,
                "windHeading": wind_heading,
                "windKts": wind_speed,
                "tow": weight,
                "baro": current_weather.press.value("HPA"),
                "oat": current_weather.temp.value("C"),
                "flaps": int(flaps),
                "antiIce": anti_ice,
                "packs": packs,
                "toga": False,
                "runwayCondition": runway_condition,
            }
        )

        flex = FlexMath.calculateFlexDist(settings, a20n)
        # VR and V2 only, V1 comes from the accelerate-stop check
        v_speeds = FlexMath.CalculateVSpeeds(
            settings.availRunway,
            settings.requiredRunway,
            settings.tow,
            settings.flaps,
            settings.runwayAltitude,
            settings.isMeters,
            settings.isKG,
            a20n,
        )

        def accelerate_stop_v1(required_runway: float):
            return FlexMath.V1SpeedVer2(
                settings.runwayAltitude,
                settings.availRunway,
                required_runway,
                settings.oat,
                settings.baro,
                settings.runwayCondition,
                settings.windHeading,
                settings.windKts,
                settings.runwayHeading,
                settings.flaps,
                FlexMath.parseWeight(settings.tow, settings.isKG),
                v_speeds.vr,
                a20n,
            )

        v1 = accelerate_stop_v1(flex.requiredRunway)
        # No abort speed of at least 100kts at flex thrust, so retry with TOGA
        use_toga = v1 == -1 or flex.flex < flex.minFlex
        if v1 == -1:
            v1 = accelerate_stop_v1(flex.togaRequiredRunway)

        required = flex.togaRequiredRunway if use_toga else flex.requiredRunway
        return FlexVSpeeds(
            flex=None if use_toga else flex.flex,
            availRunway=int(settings.availRunway),
            requiredRunway=int(required * 3.28084),
            invalid=v1 == -1
            or flex.togaRequiredRunway * 3.28084 > settings.availRunway,
            v1=v1,
            vr=v_speeds.vr,
            v2=v_speeds.v2,
            icao=icao_code,
            runwayName=runway_name,
            runwayHeading=runway.heading,
            windHeading=wind_heading,
            windKts=wind_speed,
            windVariable=wind_dir is None and wind_speed > 0,
        )


if __name__ == "__main__":
    rest = REST()
    weather = Weather()
    apt = APT()
    to = TOCalculator(rest, apt, weather)
    loop = asyncio.new_event_loop()

    async def moo():
        values = await to.get_weight_cg()
        print(values)
        trim = await to.calc_trim()
        result = await to.calc_vspeeds_flex("LFLL", "RW17L", 1, 0)
        print(trim, result)

    loop.run_until_complete(moo())
