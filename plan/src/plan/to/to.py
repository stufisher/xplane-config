# https://github.com/jbud/Flex-Calculator-TS/pull/14
# https://developer.x-plane.com/article/airport-data-apt-dat-12-00-file-format-specification/
# https://github.com/jbud/Flex-Calculator-TS/blob/master/src/airframes/a20n.ts
import asyncio
from dataclasses import dataclass, asdict


from ..rest import REST
from ..apt import APT
from ..weather import Weather
from .flex import FlexMath, calculate_trim, TakeoffInstance, VSpeeds
from .airframe import a20n


@dataclass
class FlexVSpeeds(VSpeeds):
    flex: int | None


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
        runway = self._apt.get_runway_heading_and_length(icao_code, runway_name)

        settings = TakeoffInstance(
            **{
                "availRunway": runway.length,# * 3.28084,
                "isMeters": True,
                "runwayHeading": runway.heading,
                "runwayAltitude": runway.elevation,
                "windHeading": current_weather.wind_dir.value(),
                "windKts": current_weather.wind_speed.value(),
                "tow": weight,
                "baro": current_weather.press.value(),
                "oat": current_weather.temp.value(),
                "flaps": flaps,
                "antiIce": anti_ice,
                "packs": packs,
                "toga": False,
                "runwayCondition": runway_condition,
            }
        )

        flex = FlexMath.calculateFlexDist(settings, a20n)
        asd = flex.togaRequiredRunway if flex.flex < flex.minFlex else flex.requiredRunway
        v_speeds = FlexMath.CalculateVSpeeds(
            settings.availRunway,
            settings.requiredRunway,
            settings.tow,
            settings.flaps,
            settings.runwayAltitude,
            settings.isMeters,
            settings.isKG,
            a20n,
            ASD=asd
        )

        return FlexVSpeeds(
            flex=flex.flex if flex.flex > flex.minFlex else None, **asdict(v_speeds)
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
