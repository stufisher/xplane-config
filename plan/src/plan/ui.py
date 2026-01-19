from contextlib import contextmanager
from datetime import datetime, timezone
import logging

from nicegui import ui, app

from .plan import Plan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)


SVG_DIAMOND = '<svg version="1.0" xmlns="http://www.w3.org/2000/svg" width="80" height="80"><polygon points="0 40,40 80,80 40,40 0" style=" fill: purple; stroke:black;"/></svg>'
SVG_PLANE = '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" width="123" height="123"><path d="M16.63,105.75c0.01-4.03,2.3-7.97,6.03-12.38L1.09,79.73c-1.36-0.59-1.33-1.42-0.54-2.4l4.57-3.9 c0.83-0.51,1.71-0.73,2.66-0.47l26.62,4.5l22.18-24.02L4.8,18.41c-1.31-0.77-1.42-1.64-0.07-2.65l7.47-5.96l67.5,18.97L99.64,7.45 c6.69-5.79,13.19-8.38,18.18-7.15c2.75,0.68,3.72,1.5,4.57,4.08c1.65,5.06-0.91,11.86-6.96,18.86L94.11,43.18l18.97,67.5 l-5.96,7.47c-1.01,1.34-1.88,1.23-2.65-0.07L69.43,66.31L45.41,88.48l4.5,26.62c0.26,0.94,0.05,1.82-0.47,2.66l-3.9,4.57 c-0.97,0.79-1.81,0.82-2.4-0.54l-13.64-21.57c-4.43,3.74-8.37,6.03-12.42,6.03C16.71,106.24,16.63,106.11,16.63,105.75 L16.63,105.75z" style=" fill: orange; stroke:black;"/></svg>'
ICON_DIAMOND = (
    f"L.icon({{iconSize: [12, 12], iconUrl: 'data:image/svg+xml,{SVG_DIAMOND}'}})"
)
ICON_PLANE = (
    f"L.icon({{iconSize: [24, 24], iconUrl: 'data:image/svg+xml,{SVG_PLANE}'}})" ""
)


@contextmanager
def disable(button: ui.button):
    button.disable()
    try:
        yield
    finally:
        button.enable()


class UI:
    def __init__(self):
        self._plan = Plan()
        self._background_running = True
        self._map_markers = []

    async def main(self):
        await self._plan._init()
        ui.page_title("X-Plane")

        with ui.row():
            with ui.column():
                with ui.row():
                    self._plan_select = ui.select([], on_change=self.select_plan)
                    ui.button("", icon="refres", on_click=lambda: self.update_plans())

                with ui.row():
                    self._flight_no = ui.input("A123", placeholder="Flight No.")
                    self._cruise_alt = ui.input(
                        None, placeholder="Cruise Alt", prefix="FL"
                    )
                    ui.button("MCDU Init", on_click=lambda e: self.init_mcdu(e.sender))

                current_time_label = ui.label()
                self._plan_detail = ui.label("")

                ui.label("Departure Weather")
                self.dep_weather = ui.markdown("")

                ui.label("Desination Weather")
                self.des_weather = ui.markdown("")

            with ui.element("div"):
                loc = await self._plan.location
                self._map = ui.leaflet(
                    center=(loc.latitude, loc.longitude),
                    additional_resources=[
                        "https://unpkg.com/leaflet-rotatedmarker@0.2.0/leaflet.rotatedMarker.js",
                    ],
                ).style("width: 450px; height: 450px")

        self.update_plans()

        ui.timer(
            1.0,
            lambda: current_time_label.set_text(f"{datetime.now(timezone.utc):%X} UTC"),
        )
        ui.timer(10, lambda: self._background_task())

        self._aircraft_marker = self._map.marker(
            latlng=(loc.latitude, loc.longitude),
            options={
                "rotationOrigin": "center center",
                "rotationAngle": loc.psi - 45,
            },
        )
        await self._map.initialized()
        self._aircraft_marker.run_method(":setIcon", ICON_PLANE)

    def update_plans(self):
        opts = {}
        for plan in self._plan.plans:
            opts[plan["file_path"]] = plan["departure"] + " -> " + plan["destination"]

        self._plan_select.set_options(opts, value=list(opts.keys())[0])

    async def _background_task(self):
        self.update_weather()
        await self.update_location()

    async def init_mcdu(self, element):
        with disable(element):
            await self._plan.mcdu_init(
                flt_number=self._flight_no.value, cruise_alt=self._cruise_alt.value
            )
            await self._plan.mcdu_perf()
            await self._plan.mcdu_fpln()

    async def update_location(self):
        loc = await self._plan.location
        self._map.set_center((loc.latitude, loc.longitude))
        self._aircraft_marker.move(loc.latitude, loc.longitude)
        self._aircraft_marker.run_method("setRotationAngle", loc.psi - 45)

    def update_weather(self):
        if self._plan.weather_des:
            self.des_weather.content = f"""{self._plan.weather_des.time}\n
{self._plan.weather_des.temp.string('C')} {self._plan.weather_des.press.string("mb")} {self._plan.weather_des.present_weather()} 

"""
        if self._plan.weather_dep:
            self.dep_weather.content = f"""{self._plan.weather_dep.time}\n
{self._plan.weather_dep.temp.string('C')} {self._plan.weather_dep.press.string("mb")} {self._plan.weather_dep.present_weather()}
"""

    def select_plan(self, change_event):
        self._plan.load_plan(change_event.value)
        self.update_weather()

        self._plan_detail.set_text(
            f"DEPRWY: {self._plan.current['DEPRWY']} SID: {self._plan.current['SID']} STAR: {self._plan.current.get('STAR')} APP: {self._plan.current.get('APP')} DESRWY: {self._plan.current['DESRWY']}"
        )
        self._cruise_alt.value = self._plan.cruise

        for marker in self._map_markers:
            self._map.remove_layer(marker)
        self._map_markers = []

        for waypoint in self._plan.current["waypoints"]:
            marker = self._map.marker(latlng=(waypoint.latitude, waypoint.longitude))
            self._map_markers.append(marker)
            marker.run_method(":setIcon", ICON_DIAMOND)

    async def shutdown(self):
        await self._plan.shutdown()


def main(reload=False):
    ui_inst = UI()
    app.on_shutdown(ui_inst.shutdown)
    ui.run(ui_inst.main, show=False)


if __name__ in {"__main__", "__mp_main__"}:
    main(True)
