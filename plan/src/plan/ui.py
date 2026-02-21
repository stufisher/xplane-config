from contextlib import contextmanager
import logging
import os
import webbrowser

from nicegui import ui, app, events
from nicegui.element import Element

from .plan import Plan
from .udp import UDP
from .apt import APT
from .fms import latlon_to_fms

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


class LogElementHandler(logging.Handler):
    """A logging handler that emits messages to a log element."""

    def __init__(self, element: ui.log, level: int = logging.NOTSET) -> None:
        self.element = element
        super().__init__(level)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            level_styles = {
                "ERROR": "text-red",
                "WARNING": "text-orange",
                "INFO": "text-gray",
            }
            self.element.push(msg, classes=level_styles.get(record.levelname, "INFO"))
        except Exception:
            self.handleError(record)


class Row(Element):
    def __init__(self) -> None:
        super().__init__(tag="div")
        # self.style("display: flex; flex: 1; gap: var(--nicegui-default-gap);")
        self.classes("flex flex-1 gap-(--nicegui-default-gap)")


class Col(Element):
    def __init__(self, gap=1) -> None:
        super().__init__(tag="div")
        # self.style(f"flex-direction: column; display: flex; flex: 1; gap: {gap}rem")
        self.classes(f"flex-col flex flex-1 gap-{gap*3}")


class Card(ui.card):
    def __init__(self, grow=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.style("gap: 0.5rem; align-items: normal;" + (" flex: 1; " if grow else ""))
        self.style("align-items: normal")
        self.classes("items-baseline gap-1" + (" flex-1" if grow else ""))


class ToggleButton(ui.button):
    def __init__(self, *args, state=False, **kwargs) -> None:
        self._state = state
        super().__init__(*args, **kwargs)
        self.on("click", self.toggle)

    @property
    def value(self):
        return self._state

    def toggle(self) -> None:
        self._state = not self._state
        self.update()

    def update(self) -> None:
        with self.props.suspend_updates():
            self.props(f'color={"secondary" if self._state else "primary"}')
        super().update()


class UI:
    def __init__(self):
        self._apt = APT()
        self._plan = Plan(self._apt)
        self._udp = UDP(self._apt)
        self._background_running = True
        self._map_markers = []
        self._log_handler = None

    async def main(self):
        await self._plan._init()
        app.on_shutdown(self._plan.shutdown)
        app.add_static_files("/assets", os.path.dirname(__file__) + "/../../assets")
        ui.page_title("X-Plane")

        # @ui.page("/")
        # async def page():
        if True:
            if 1:
                dark = ui.dark_mode()
                dark.enable()
                ui.add_css(
                    ".leaflet-control-zoom-in, .leaflet-control-zoom-out, .leaflet-control-attribution, .leaflet-layer { filter: invert(100%) hue-rotate(180deg) brightness(90%) contrast(90%); }"
                )

            ui.add_css(
                """
                @font-face{
                    font-family: "DSEG7";
                    src: url('/assets/DSEG7ClassicMini-Regular.ttf') format('truetype');
                    font-weight: normal;
                    font-style: normal;
                }
                .nicegui-markdown p {
                    margin-top: 0;
                }
                .leaflet-tooltip.leaflet-tooltip-right {
                    background: none;
                    border: none;
                    padding: 0 6px;
                    color: pink;
                    margin-left: 0;
                }

                .leaflet-tooltip-right:before {
                    border: none !important;
                }
            """
            )
            ui.query(".nicegui-content").classes("flex-row")

            with Row():
                with Col():
                    with Card():
                        with Row().classes("flex-nowrap"):
                            self._plan_select = ui.select(
                                [], on_change=self.select_plan
                            ).classes("flex-1")
                            with ui.button_group():
                                plan_refresh_buttton = ui.button(
                                    icon="refresh",
                                    on_click=lambda e: self.update_plans(),
                                )
                                plan_refresh_buttton.tooltip("Refresh plans")
                        with Row().classes("flex-nowrap"):
                            self._flight_no = ui.input(
                                "Flight No.", value="A123", placeholder="Flight No."
                            )
                            self._code_code = ui.input(
                                "Cost", value="20", placeholder="Cost Code"
                            )
                            self._cruise_alt = ui.input(
                                "Cruise Alt.",
                                value="",
                                placeholder="Cruise Alt",
                                prefix="FL",
                            )
                            self._to_flaps = ui.select(
                                {1: "1+F", 2: "2", 3: "3"},
                                label="Flaps",
                                value=1,
                                on_change=self.update_mcdu_perf,
                            )
                            with ui.button_group():
                                self._runway_condition = ToggleButton(
                                    icon="umbrella", on_click=self.update_mcdu_perf
                                )
                                self._runway_condition.tooltip("Runway Wet")
                                self._packs = ToggleButton(
                                    icon="hvac",
                                    on_click=self.update_mcdu_perf,
                                    state=True,
                                )
                                self._packs.tooltip("Packs")
                                self._anti_ice = ToggleButton(
                                    icon="ac_unit", on_click=self.update_mcdu_perf
                                )
                                self._anti_ice.tooltip("Anti Ice")
                    with Card(grow=True):
                        with Row():
                            # with Col(gap=0):
                            self._time_label = (
                                ui.label("12:34")
                                .style("font-family: DSEG7; font-size: 1.5rem")
                                .classes("flex-1")
                            )
                            ui.timer(1.0, self.update_time)
                            with ui.button_group():
                                restore_popups_button = ui.button(
                                    icon="window",
                                    on_click=self.restore_popups,
                                )
                                restore_popups_button.tooltip("Restore popups")
                                self._map_click_to_scratchpad = ToggleButton(
                                    icon="add_location"
                                )
                                self._map_click_to_scratchpad.tooltip(
                                    "Enable map click to scratchpad"
                                )
                                clear_scratchpad = ui.button(
                                    icon="backspace",
                                    on_click=lambda: self._plan._rest.clear_scratchpad(),
                                )
                                clear_scratchpad.tooltip("Clear scratchpad")
                                self._map_center = ToggleButton(
                                    icon="my_location",
                                    state=True,
                                    on_click=lambda: self.update_location(),
                                )
                                self._map_center.tooltip("Center map on plane location")
                        with Row():
                            self._plan_detail = (
                                ui.markdown("")
                                .classes("flex-1")
                                .style("font-size: 1rem;")
                            )
                            with ui.button_group():
                                mcdu_init_button = ui.button(
                                    icon="computer",
                                    on_click=lambda e: self.init_mcdu(e.sender),
                                )
                                mcdu_init_button.tooltip("Init MCDU")
                                spawn_aircaft_button = ui.button(
                                    icon="add_road",
                                    on_click=self.move_aircraft_to_runway,
                                )
                                spawn_aircaft_button.tooltip(
                                    "Spawn aircraft at departure airport runway"
                                )
                                spawn_aircaft_gate_button = ui.button(
                                    icon="luggage",
                                    on_click=self.move_aircraft_to_gate,
                                )
                                spawn_aircaft_gate_button.tooltip(
                                    "Spawn aircraft at departure airport gate"
                                )
                        with Row():
                            self._route = ui.input("Route", value="").classes("flex-1")
                            copy_route_button = ui.button(
                                icon="content_paste",
                                on_click=lambda: ui.clipboard.write(self._route.value),
                            )
                            copy_route_button.tooltip("Copy route to clipboard")
                        with Row():
                            with Col(gap=0):
                                with Row():
                                    ui.icon("flight_takeoff").classes("text-2xl")
                                    self.dep_time = ui.label("--:--")
                                self.dep_weather = ui.markdown("-4c mist 1016mb")

                            with Col(gap=0):
                                with Row():
                                    ui.icon("flight_land").classes("text-2xl")
                                    self.des_time = ui.label("--:--")
                                self.des_weather = ui.markdown("6c hail 999mb")

                    with Card(grow=True):
                        self._log = ui.log(max_lines=5).style("height: 80px")

                with Card(grow=True):
                    loc = await self._plan.location

                    self._map = ui.leaflet(
                        center=(
                            loc.latitude if loc.latitude is not None else 0,
                            loc.longitude if loc.longitude is not None else 0,
                        ),
                        additional_resources=[
                            "https://unpkg.com/leaflet-rotatedmarker@0.2.0/leaflet.rotatedMarker.js",
                        ],
                    ).classes("flex-1")

            self.update_plans()
            ui.timer(10, lambda: self._background_task())
            self._aircraft_marker = self._map.marker(
                latlng=(
                    loc.latitude if loc.latitude else 0,
                    loc.longitude if loc.longitude else 0,
                ),
                options={
                    "rotationOrigin": "center center",
                    "rotationAngle": (loc.psi - 45) if loc.psi is not None else 0,
                },
            )
            await self._map.initialized()
            self._map.on("map-click", self.on_map_click)
            self._aircraft_marker.run_method(":setIcon", ICON_PLANE)

            self._log_handler = LogElementHandler(self._log)
            logging.getLogger().addHandler(self._log_handler)
            # ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

    def update_plans(self):
        opts = {}
        plans = sorted(self._plan.plans, key=lambda d: d["departure"])
        for plan in plans:
            opts[plan["file_path"]] = plan["departure"] + " -> " + plan["destination"]

        self._plan_select.set_options(opts, value=list(opts.keys())[0])

    async def _background_task(self):
        self.update_weather()
        await self.update_location()

    async def init_mcdu(self, element):
        with disable(element):
            await self._plan.mcdu_init(
                flt_number=self._flight_no.value,
                cruise_alt=self._cruise_alt.value,
                cost=self._code_code.value,
            )
            await self.update_mcdu_perf()
            await self._plan.mcdu_fpln()

    async def update_mcdu_perf(self):
        await self._plan.mcdu_perf(
            to_flaps=self._to_flaps.value,
            runway_condition=1 if self._runway_condition.value else 0,
            packs=self._packs.value,
            anti_ice=self._anti_ice.value,
        )

    async def update_location(self):
        loc = await self._plan.location
        if loc.latitude is None:
            return
        if self._map_center.value:
            self._map.set_center((loc.latitude, loc.longitude))
        self._aircraft_marker.move(loc.latitude, loc.longitude)
        self._aircraft_marker.run_method("setRotationAngle", loc.psi - 45)

    def update_weather(self):
        if self._plan.weather_dep:
            self.dep_time.set_text(
                f"{self._plan.current['ADEP']} {self._plan.weather_dep.time:%H:%M}"
            )
            self.dep_weather.content = f"{self._plan.weather_dep.temp.string('C')}, {self._plan.weather_dep.wind()}, {self._plan.weather_dep.visibility()} {self._plan.weather_dep.press.string("mb")} {self._plan.weather_dep.present_weather()}"
        else:
            self.dep_time.set_text(f"{self._plan.current['ADEP']} --:--")
            self.dep_weather.content = "N/A"
        if self._plan.weather_des:
            self.des_time.set_text(
                f"{self._plan.current['ADES']} {self._plan.weather_des.time:%H:%M}"
            )
            self.des_weather.content = f"{self._plan.weather_des.temp.string('C')}, {self._plan.weather_des.wind()}, {self._plan.weather_des.visibility()} {self._plan.weather_des.press.string("mb")} {self._plan.weather_des.present_weather()}"
        else:
            self.des_time.set_text(f"{self._plan.current['ADES']} --:--")
            self.des_weather.content = "N/A"

    async def update_time(self):
        zulu_seconds = await self._plan.time
        if zulu_seconds is None:
            self._time_label.set_text("--:--:--")
            return
        hours, remain = divmod(int(zulu_seconds), 3600)
        minutes, seconds = divmod(remain, 60)
        self._time_label.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    async def select_plan(self, change_event):
        self._plan.load_plan(change_event.value)
        self.update_weather()

        self._plan_detail.content = f"**DEPRW**: {self._plan.current.get('DEPRWY')} **SID**: {self._plan.current.get('SID')} **STAR**: {self._plan.current.get('STAR')} **APP**: {self._plan.current.get('APP')} **DESRW**: {self._plan.current.get('DESRWY')}"

        self._cruise_alt.value = self._plan.cruise

        for marker in self._map_markers:
            try:
                self._map.remove_layer(marker)
            except Exception:
                logger.debug("Could not remove existing marker")
        self._map_markers = []

        # await self._map.initialized()

        route = []
        for waypoint in self._plan.current["waypoints"]:
            route.append(waypoint.name)
            marker = self._map.marker(latlng=(waypoint.latitude, waypoint.longitude))
            self._map_markers.append(marker)
            marker.run_method(":setIcon", ICON_DIAMOND)
            marker.run_method(
                "bindTooltip",
                waypoint.name,
                {
                    "permanent": True,
                    "direction": "right",
                    "className": "leaflet-tooltip-nicegui",
                },
            )

        self._route.value = " ".join(route)

    def move_aircraft_to_runway(self):
        runway = self._plan.current["DEPRWY"]
        icao_code = self._plan.current["ADEP"]
        if runway and icao_code:
            self._udp.move_aircraft_to_runway(icao_code, runway)

    def move_aircraft_to_gate(self):
        icao_code = self._plan.current["ADEP"]
        if icao_code:
            self._udp.move_aircraft_to_gate(icao_code)

    async def restore_popups(self):
        await self._plan._rest.execute_command("toliss_airbus/reinstatePopups")

    async def on_map_click(self, e: events.GenericEventArguments):
        if self._map_click_to_scratchpad.value:
            sp = latlon_to_fms(e.args["latlng"]["lat"], e.args["latlng"]["lng"])
            await self._plan._rest.write_scratchpad(sp)

    async def shutdown(self):
        if self._log_handler:
            logger.removeHandler(self._log_handler)
        await self._plan.shutdown()


def main(reload=False):
    ui_inst = UI()
    cmd = [
        "open",
        "-na",
        "Google Chrome",
        "--args",
        "--app=%s",
        "--user-data-dir=/tmp/chrome-kiosk-{uuid4()}",
    ]
    webbrowser.register(
        "kiosk", None, webbrowser.BackgroundBrowser(cmd), preferred=True
    )
    app.on_shutdown(ui_inst.shutdown)
    ui.run(ui_inst.main, reload=reload, show=True)


if __name__ in {"__main__", "__mp_main__"}:
    main(True)
