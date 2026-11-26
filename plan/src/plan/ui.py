import argparse
import asyncio
import base64
from contextlib import contextmanager
import logging
import os
import time
import uuid
import webbrowser

from nicegui import Client, ui, app, events, run
from nicegui.element import Element

from .plan import Plan
from .udp import UDP
from .apt import APT
from .fms import latlon_to_fms
from .generate import Generator, runway_heading
from .divert import Divert, next_phase, path_text, plan_route, speeds, vectors
from .divert_view import DivertDialog, ils_text
from .enroute import (
    enroute_hazards,
    enroute_text,
    enroute_wind,
    path_waypoints,
    position_along,
    route_length,
    route_points,
)
from .generate_view import (
    PlannerDialog,
    approach_colour,
    approach_tip,
    severity_colour,
)
from .weather import HAZARD_ICONS, challenge, is_wet, metar_wind
from .grib import WindsAloft, latest_grib
from .places import download_missing
from .to.airframe import a20n
from .to.view import takeoff_svg
from .xplane import DEFAULT_XPLANE_DIR, XPlanePaths

APPROACH_HELP = """
**Flying a 3° approach**

- **FPA:** push TRK-FPA and set −3.0; it holds the path at any speed.
  Hand flying, keep the bird just below the 2.5° mark.
- **ILS:** on the intercept heading push APPR to capture LOC and G/S.
- **Check height against distance:** about 300ft per nm above the runway.

| Distance | Height |
|---|---|
| 10nm | 3200ft |
| 5nm | 1600ft |
| 3nm | 950ft |
| 2nm | 650ft |

High: steepen a little; low: shallow a little; then back to −3°.

- **VS:** height × ground speed ÷ (60 × distance), or ground speed × 5.3 on
  a 3° path; final ground speed is Vapp − headwind.
- **Distance:** LS on shows the ILS DME on the PFD; the ND shows the
  distance to the runway when it is in the FPLN.
"""

# Chrome app window size that fits the whole UI
DEFAULT_WINDOW_SIZE = "956x652"
# Seconds to wait after the last window disconnects before exiting, as a
# reload disconnects briefly before the page connects again
EXIT_GRACE_S = 5

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)


SVG_DIAMOND = (
    lambda color: f'<svg version="1.0" xmlns="http://www.w3.org/2000/svg" width="80" height="80"><polygon points="0 40,40 80,80 40,40 0" style=" fill: {color}; stroke:black;"/></svg>'
)
SVG_PLANE = '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" width="123" height="123"><path d="M16.63,105.75c0.01-4.03,2.3-7.97,6.03-12.38L1.09,79.73c-1.36-0.59-1.33-1.42-0.54-2.4l4.57-3.9 c0.83-0.51,1.71-0.73,2.66-0.47l26.62,4.5l22.18-24.02L4.8,18.41c-1.31-0.77-1.42-1.64-0.07-2.65l7.47-5.96l67.5,18.97L99.64,7.45 c6.69-5.79,13.19-8.38,18.18-7.15c2.75,0.68,3.72,1.5,4.57,4.08c1.65,5.06-0.91,11.86-6.96,18.86L94.11,43.18l18.97,67.5 l-5.96,7.47c-1.01,1.34-1.88,1.23-2.65-0.07L69.43,66.31L45.41,88.48l4.5,26.62c0.26,0.94,0.05,1.82-0.47,2.66l-3.9,4.57 c-0.97,0.79-1.81,0.82-2.4-0.54l-13.64-21.57c-4.43,3.74-8.37,6.03-12.42,6.03C16.71,106.24,16.63,106.11,16.63,105.75 L16.63,105.75z" style=" fill: orange; stroke:black;"/></svg>'
ICON_DIAMOND = lambda color: (
    f"L.icon({{iconSize: [12, 12], iconUrl: 'data:image/svg+xml,{SVG_DIAMOND(color)}'}})"
)
ICON_PLANE = (
    f"L.icon({{iconSize: [24, 24], iconUrl: 'data:image/svg+xml,{SVG_PLANE}'}})" ""
)
TOOLTIP_OPTIONS = {
    "permanent": True,
    "direction": "right",
    "className": "leaflet-tooltip-nicegui",
}
SEGMENT_COLOURS = {
    "SID": "cyan",
    "ENRT": "green",
    "STAR": "purple",
    "APP": "magenta",
}


def weather_text(metar) -> str:
    """Format a METAR for display; temp and press are absent from some reports."""
    parts = [
        metar.temp.string("C") if metar.temp else None,
        metar.wind(),
        metar.visibility(),
        metar.press.string("mb") if metar.press else None,
        metar.present_weather(),
    ]
    return ", ".join(part for part in parts if part)


def plan_detail(plan) -> tuple[str, tuple[str, str, str]]:
    """Departure line, and the arrival line split around the approach so it
    can be coloured; each in the order it is flown, a transition as NAME.TRANS"""

    def named(name, trans):
        if not name:
            return "-"
        return f"{name}.{trans}" if trans else name

    def runway(name, length):
        return f"{name or '-'} ({length or '-'}ft)"

    dep = f"{runway(plan.DEPRWY, plan.DEPRWY_LENGTH)} · {named(plan.SID, plan.SIDTRANS)}"
    arr = (
        f"ARR {named(plan.STAR, plan.STARTRANS)} ·",
        named(plan.APP, plan.APPTRANS),
        f"· {runway(plan.DESRWY, plan.DESRWY_LENGTH)}",
    )
    return f"DEP {dep}", arr


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
        self.classes("flex flex-1 gap-(--nicegui-default-gap)")


class Col(Element):
    def __init__(self, gap=1) -> None:
        super().__init__(tag="div")
        self.classes(f"flex-col flex flex-1 gap-{gap*3}")


class Card(ui.card):
    def __init__(self, grow=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
    def __init__(self, paths: XPlanePaths = XPlanePaths()):
        self._apt = APT(paths)
        self._plan = Plan(self._apt, self.update_time, self.update_location, paths)
        self._udp = UDP(self._apt)
        self._generator = Generator(paths)
        self._divert = Divert(self._generator)
        # Airport label and runway being diverted to, None when not diverting
        self._divert_target = None
        self._divert_layers = []
        # Route length when the diversion started, for its progress bar
        self._divert_total = None
        # Fixed points of the diversion, set from the first position, and the
        # leg being flown
        self._divert_route = None
        self._divert_phase = "direct"
        self._paths = paths
        self._winds_aloft = None
        self._background_running = True
        self._map_markers = []
        self._map_lines = []
        self._log_handler = None
        self._last_location_update_time = 0
        self._map_center = None
        self._time_label = None

    async def startup(self):
        await self._plan._init()

    def page(self):
        ui.page_title("X-Plane")
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
                        self._plan_select = (
                            ui.select(
                                [],
                                on_change=lambda e: self.select_plan(e.value),
                                with_input=True,
                            )
                            .classes("flex-1 w-50")
                        )
                        self._spinner = ui.spinner(size="lg")
                        self._spinner.set_visibility(False)
                        with ui.button_group():
                            plan_refresh_button = ui.button(
                                icon="refresh",
                                on_click=lambda e: self.update_plans(),
                            )
                            plan_refresh_button.tooltip("Refresh plans")
                            divert_button = ui.button(
                                icon="alt_route", on_click=self.open_divert
                            )
                            divert_button.tooltip("Divert to a nearby airport")
                            planner_button = ui.button(
                                icon="table_view", on_click=self.open_planner
                            )
                            planner_button.tooltip("Plans table and new plans")
                            help_button = ui.button(
                                icon="help_outline", on_click=lambda: self._help_dialog.open()
                            )
                            help_button.tooltip("Flying a 3° approach")
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
                        self._time_label = (
                            ui.label("--:--:--")
                            .style("font-family: DSEG7; font-size: 1.5rem")
                            .classes("flex-1")
                        )
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
                        # The text wraps beside the buttons rather than pushing
                        # them onto a line of their own
                        with ui.column().classes("flex-1 min-w-0 gap-0").style(
                            "font-size: 0.85rem;"
                        ):
                            self._plan_dep = ui.label("").classes("w-full")
                            with ui.row().classes("w-full gap-x-1 gap-y-0"):
                                self._plan_arr = ui.label("")
                                self._plan_app = ui.label("")
                                with self._plan_app:
                                    # Every runway's wind and approaches
                                    self._plan_app_tip = ui.tooltip("").style(
                                        "white-space: pre-line"
                                    )
                                self._plan_arr_end = ui.label("")
                        with ui.button_group().classes("shrink-0"):
                            mcdu_init_button = ui.button(
                                icon="computer",
                                on_click=lambda e: self.init_mcdu(e.sender),
                            )
                            mcdu_init_button.tooltip("Init MCDU")
                            self._takeoff_button = ui.button(
                                icon="air", on_click=self.show_takeoff
                            )
                            self._takeoff_button.tooltip("Runway and wind")
                            self._takeoff_button.disable()
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
                    self._enroute_weather = ui.label("").classes("text-sm")
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        self._progress_dep = ui.label("").classes("text-xs")
                        # Track of the whole route: flown part filled, hazards and
                        # the strongest wind marked where they are
                        self._progress_bar = (
                            ui.element("div")
                            .classes("flex-1 relative")
                            .style(
                                "height: 8px; background: #555; border-radius: 4px"
                            )
                        )
                        self._progress_arr = ui.label("").classes("text-xs")
                        self._progress_text = ui.label("").classes("text-xs")
                    self._progress_key = None
                    # Vectors to a diversion runway, shown while diverting
                    with ui.row().classes("w-full items-start no-wrap") as self._divert_box:
                        with ui.column().classes("flex-1 min-w-0 gap-0").style(
                            "font-size: 0.85rem; color: orange"
                        ):
                            self._divert_title = ui.label("")
                            # One bullet per leg still to fly
                            self._divert_legs = ui.label("").style(
                                "white-space: pre-line"
                            )
                            # Live height against the glide path, on hover
                            self._divert_path = ui.tooltip("").style(
                                "font-size: 0.85rem"
                            )
                        ui.button(icon="close", on_click=self.clear_divert).props(
                            "flat round dense"
                        ).tooltip("Stop diverting")
                    self._divert_box.set_visibility(False)

                with Card(grow=True):
                    log = ui.log(max_lines=5).style("height: 80px")
                    log_handler = LogElementHandler(log)
                    logging.getLogger().addHandler(log_handler)
                    ui.context.client.on_disconnect(
                        lambda: logging.getLogger().removeHandler(log_handler)
                    )

            with Card(grow=True):
                loc = self._plan.location

                self._map = ui.leaflet(
                    center=(
                        loc.latitude if loc.latitude is not None else 0,
                        loc.longitude if loc.longitude is not None else 0,
                    ),
                    additional_resources=[
                        "https://unpkg.com/leaflet-rotatedmarker@0.2.0/leaflet.rotatedMarker.js",
                    ],
                ).classes("flex-1")

                aircraft_marker = self._map.marker(
                    latlng=(
                        loc.latitude if loc.latitude else 0,
                        loc.longitude if loc.longitude else 0,
                    ),
                    options={
                        "rotationOrigin": "center center",
                        "rotationAngle": (
                            (loc.psi - 45) if loc.psi is not None else 0
                        ),
                    },
                )
                self._aircraft_marker = aircraft_marker
                self._map.on("map-click", self.on_map_click)
                # The icon is not part of the marker's serialised state, so the map
                # re-adds it as a default pin every time it initialises
                self._map.on(
                    "init", lambda: aircraft_marker.run_method(":setIcon", ICON_PLANE)
                )
        with ui.dialog() as self._help_dialog, ui.card():
            ui.markdown(APPROACH_HELP)
        with ui.dialog() as self._takeoff_dialog:
            self._takeoff_card = ui.card()
        self._divert_dialog = DivertDialog(
            self._divert,
            self._generator,
            location=lambda: self._plan.location,
            metar=self.metar,
            speeds=lambda wind, runway: speeds(
                a20n,
                self._plan.weight_kg or a20n.mlw,
                wind,
                runway,
                self._plan.landing_conf,
            ),
            on_divert=self.start_divert,
        )
        self._planner = PlannerDialog(
            self._generator,
            plans=lambda: self._plan.plans,
            location=self.aircraft_position,
            metar=self.metar,
            winds=self.winds_aloft,
            stations=self.metar_stations,
            on_select=self.show_plan,
            on_generated=self.plan_generated,
        )

        self.update_plans()
        ui.timer(10, lambda: self._background_task())

    def update_plans(self):
        opts = {}
        plans = sorted(self._plan.plans, key=lambda d: d.departure_board)
        for plan in plans:
            opts[plan.file_path] = f"{plan.departure_board} -> {plan.destination_board}"

        self._plan_select.set_options(opts, value=list(opts.keys())[0])

    def aircraft_position(self):
        loc = self._plan.location
        if loc.latitude is None:
            return None
        return loc.latitude, loc.longitude

    def metar(self, icao: str):
        """Latest METAR from the sim's real weather, None without one"""
        try:
            return self._plan.forecast(icao)
        except Exception:
            logger.debug(f"No weather for {icao}")
            return None

    def winds_aloft(self):
        """Winds from the newest real weather GRIB, reloaded when it changes"""
        path = latest_grib(self._paths.real_weather)
        if path is None:
            return None
        if self._winds_aloft is None or self._winds_aloft.path != path:
            try:
                self._winds_aloft = WindsAloft(path)
            except (OSError, ValueError, IndexError):
                logger.warning(f"Could not read winds from {path}")
                return None
        return self._winds_aloft

    def metar_stations(self):
        """ICAO -> (lat, lon) of every airport with a METAR"""
        try:
            codes = self._plan.metar_stations()
        except Exception:
            logger.debug("No METAR stations")
            return {}
        return self._generator.positions(codes)

    async def open_planner(self):
        await self._planner.open()

    def show_plan(self, path: str):
        self._plan_select.value = path

    def plan_generated(self, path: str):
        self.update_plans()
        self.show_plan(path)

    async def _background_task(self):
        self.update_weather()
        self.update_enroute()
        self.update_divert()

    async def open_divert(self):
        await self._divert_dialog.open()

    def start_divert(self, icao, label, runway):
        self._divert_target = (icao, label, runway)
        self._divert_total = None
        self._divert_route = None
        self._divert_phase = "direct"
        self._divert_box.set_visibility(True)
        self.update_divert()
        self.update_weather()

    def clear_divert(self):
        self._divert_target = None
        self._divert_total = None
        self._divert_box.set_visibility(False)
        self._draw_divert(None)
        self.update_weather()
        self.update_enroute()

    def update_divert(self):
        """Vectors from the aircraft to the diversion runway, kept up to date"""
        if not self._divert_target:
            return
        icao, label, runway = self._divert_target
        loc = self._plan.location
        if loc.latitude is None:
            self._divert_legs.set_text("Waiting for the aircraft position")
            return
        ground_speed = loc.groundspeed * 1.943844 if loc.groundspeed else None
        # Landing weight taken as the current weight; the MLW until the sim
        # sends it
        weight = self._plan.weight_kg or a20n.mlw
        wind = metar_wind(self.metar(icao))
        if self._divert_route is None:
            self._divert_route = plan_route(loc.latitude, loc.longitude, runway)
        self._divert_phase = next_phase(
            self._divert_route, loc.latitude, loc.longitude, self._divert_phase
        )
        v = vectors(
            loc.latitude,
            loc.longitude,
            loc.altitude_ft,
            ground_speed,
            loc.variation,
            runway,
            speeds(a20n, weight, wind, runway, self._plan.landing_conf),
            self._divert_route,
            self._divert_phase,
        )
        ils = ils_text(runway)
        direct, intercept, final = v.legs
        eta = ""
        if v.eta_min:
            eta = f", ETA {v.eta_min:.0f} min"
            if self._plan.time is not None:
                arrival = (self._plan.time + v.eta_min * 60) % 86400
                eta += f" ({int(arrival // 3600):02d}:{int(arrival % 3600 // 60):02d}Z)"
        descent = f" ({v.descent})" if v.descent else ""
        s = v.speeds
        decel = ""
        if v.decel_nm >= 1:
            decel = f", slow to {direct.speed_kt:.0f}kt in the last {v.decel_nm:.0f}nm"
        mlw = "" if self._plan.weight_kg else " MLW"
        # Only the legs still to fly
        parts = []
        if not direct.done:
            parts.append(
                f"HDG {direct.heading_mag:03.0f}° {direct.distance:.0f}nm, down to "
                f"{v.intercept_alt_ft}ft{descent}{decel}"
            )
        if not intercept.done:
            parts.append(
                f"HDG {intercept.heading_mag:03.0f}° {intercept.distance:.0f}nm at "
                f"{v.intercept_alt_ft}ft"
                + (descent if direct.done else "")
                + f", slow to {intercept.speed_kt:.0f}kt"
            )
        parts.append(
            f"FINAL {final.heading_mag:03.0f}° {final.distance:.0f}nm "
            f"({v.glide_angle:.1f}°) VAPP {s.vapp:.0f} "
            f"(VLS {s.vls:.0f} CONF {s.conf}, {s.weight_kg / 1000:.1f}t{mlw})"
        )
        self._divert_title.set_text(
            f"DIVERT {label} {runway.name} · {runway.length_ft}ft"
            + (f" · {ils}" if ils else "")
            + f" · {v.total_nm:.0f}nm{eta}"
        )
        self._divert_legs.set_text("\n".join(f"• {part}" for part in parts))
        self._draw_divert(v)
        self._show_divert_progress(v)
        self.update_divert_path()

    def _draw_divert(self, v):
        """Dashed route and its turn points on the map, None to remove them"""
        for layer in self._divert_layers:
            try:
                self._map.remove_layer(layer)
            except Exception:
                logger.debug("Could not remove divert layer")
        self._divert_layers = []
        if v is None:
            return
        self._divert_layers.append(
            self._map.generic_layer(
                name="polyline",
                args=[
                    v.points,
                    {"color": "orange", "weight": 3, "dashArray": "8 6"},
                ],
            )
        )
        for point, name in zip(v.points[1:], v.point_labels):
            marker = self._map.marker(latlng=point)
            marker.run_method(":setIcon", ICON_DIAMOND("orange"))
            marker.run_method("bindTooltip", name, TOOLTIP_OPTIONS)
            self._divert_layers.append(marker)

    def update_enroute(self):
        """Winds aloft and cruise hazards along the current plan: one line of
        text and a progress bar with the aircraft's position"""
        plan = self._plan.current
        if not plan:
            self._enroute_weather.set_text("")
            if not self._divert_target:
                self._show_progress(None, None, 0, None, [])
            return
        path = path_waypoints(plan)
        points = route_points(path, step=5)
        winds = self.winds_aloft()
        wind = enroute_wind(points, winds) if winds else None
        hazards = enroute_hazards(points, self.metar_stations(), self.metar)
        hazard = max(hazards, key=lambda h: h.challenge.score, default=None)
        text = enroute_text(wind, hazard) or "N/A"
        self._enroute_weather.set_text(f"Enroute: {text}")
        self._enroute_weather.style(
            f"color: {severity_colour(hazard.challenge.score if hazard else 0)}"
        )
        loc = self._plan.location
        position = position_along(points, loc.latitude, loc.longitude)
        if not self._divert_target:
            self._show_progress(plan, position, route_length(path), wind, hazards)

    def _show_progress(self, plan, position, total, wind, hazards):
        """Redraw the route progress bar when anything on it has changed"""

        def where(along):
            if position is None:
                return f"at {along:.0f}nm"
            ahead = along - position
            return f"{abs(ahead):.0f}nm {'ahead' if ahead >= 0 else 'behind'}"

        def percent(along):
            return 0 if not total else max(0, min(100, 100 * along / total))

        markers = [
            (
                percent(h.along),
                h.challenge.icon,
                severity_colour(h.challenge.score),
                f"{h.challenge.notes} {h.station}, {where(h.along)}",
            )
            for h in hazards
        ]
        if wind and wind.max_speed:
            markers.append(
                (
                    percent(wind.max_along),
                    "▼",
                    "white",
                    f"max wind {wind.max_direction:03.0f}/{wind.max_speed:.0f}, "
                    f"{where(wind.max_along)}",
                )
            )
        filled = percent(position) if position is not None else 0
        self._draw_progress(
            plan and plan.file_path,
            plan.ADEP if plan else "",
            plan.ADES if plan else "",
            filled,
            f"{position:.0f} / {total:.0f} nm"
            if plan and position is not None
            else f"{total:.0f} nm" if plan else "",
            markers,
        )

    def _show_divert_progress(self, v):
        """The bar as progress from where the diversion started to the runway,
        with the intercept and final marked"""
        icao, _, runway = self._divert_target
        if self._divert_total is None or v.total_nm > self._divert_total:
            self._divert_total = v.total_nm
        total = self._divert_total
        flown = total - v.total_nm

        def percent(along):
            return 0 if not total else max(0, min(100, 100 * along / total))

        _, intercept, final = v.legs
        # Turn points still ahead
        markers = []
        if v.phase == "direct":
            markers.append(
                (
                    percent(total - intercept.distance - final.distance),
                    "◆",
                    "orange",
                    f"intercept, HDG {intercept.heading_mag:03.0f}°",
                )
            )
        if v.phase != "final":
            markers.append(
                (
                    percent(total - final.distance),
                    "◆",
                    "orange",
                    f"final {final.heading_mag:03.0f}° at {v.intercept_alt_ft}ft",
                )
            )
        self._draw_progress(
            ("divert", icao, runway.name),
            "DIV",
            icao,
            percent(flown),
            f"{flown:.0f} / {total:.0f} nm",
            markers,
        )

    def _draw_progress(self, owner, left, right, filled, text, markers):
        """Redraw the progress bar when anything on it has changed"""
        key = (owner, round(filled), tuple(markers))
        if key == self._progress_key:
            return
        self._progress_key = key

        self._progress_dep.set_text(left)
        self._progress_arr.set_text(right)
        self._progress_text.set_text(text)
        self._progress_bar.clear()
        with self._progress_bar:
            ui.element("div").style(
                "position: absolute; left: 0; top: 0; bottom: 0; "
                f"width: {filled:.1f}%; background: #2196f3; border-radius: 4px"
            )
            for left, icon, colour, tip in markers:
                with ui.label(icon).style(
                    f"position: absolute; left: {left:.1f}%; top: -9px; "
                    f"transform: translateX(-50%); color: {colour}; "
                    "font-size: 13px; line-height: 1; cursor: default"
                ):
                    ui.tooltip(tip)

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
        self._spinner.set_visibility(True)
        await self._plan.mcdu_perf(
            to_flaps=self._to_flaps.value,
            runway_condition=1 if self._runway_condition.value else 0,
            packs=self._packs.value,
            anti_ice=self._anti_ice.value,
        )
        self._spinner.set_visibility(False)
        self._takeoff_button.set_enabled(self._plan.takeoff is not None)

    def show_takeoff(self):
        takeoff = self._plan.takeoff
        if takeoff is None:
            return
        # Rendered as an image so the SVG is not passed through HTML sanitising
        svg = base64.b64encode(takeoff_svg(takeoff).encode()).decode()
        self._takeoff_card.clear()
        with self._takeoff_card:
            ui.label(f"{takeoff.icao} {takeoff.runwayName}").classes("text-lg")
            ui.image(f"data:image/svg+xml;base64,{svg}").style("width: 440px")
            ui.button("Close", on_click=self._takeoff_dialog.close)
        self._takeoff_dialog.open()

    def fit_route(self):
        """Zoom the map to the whole route and stop following the aircraft,
        which the centre button turns back on"""
        points = [
            (w.latitude, w.longitude)
            for _, waypoints in self._plan.current.segments
            for w in waypoints
        ]
        if not points:
            return
        lats, lons = zip(*points)
        self._map.run_map_method(
            "fitBounds",
            [[min(lats), min(lons)], [max(lats), max(lons)]],
            {"padding": [20, 20]},
        )
        if self._map_center.value:
            self._map_center.toggle()

    def update_location(self):
        if not self._map_center:
            return
        now = time.time()
        if now - self._last_location_update_time < 1:
            return
        loc = self._plan.location
        if loc.latitude is None:
            return
        if self._map_center.value:
            self._map.set_center((loc.latitude, loc.longitude))
        self._aircraft_marker.move(loc.latitude, loc.longitude)
        self._aircraft_marker.run_method("setRotationAngle", loc.psi - 45)
        self._last_location_update_time = now
        self.update_divert_path()

    def update_divert_path(self):
        """Tooltip over the divert text with the height against the glide path"""
        if not self._divert_target:
            return
        loc = self._plan.location
        if loc.latitude is None:
            return
        self._divert_path.set_text(
            path_text(
                loc.latitude,
                loc.longitude,
                (loc.elevation or 0) * 3.28084,
                loc.groundspeed * 1.943844 if loc.groundspeed else None,
                self._divert_target[2],
            )
        )

    def update_weather(self):
        # While diverting the arrival side shows the diversion airport
        if self._divert_target:
            icao, _, runway = self._divert_target
            self._show_arrival_weather(icao, self.metar(icao), runway.name)
        if not self._plan.current:
            return
        if self._plan.weather_dep:
            self.dep_time.set_text(
                f"{self._plan.current.ADEP} {self._plan.weather_dep.time:%H:%M}"
            )
            self._show_weather(
                self.dep_weather, self._plan.weather_dep, self._plan.current.DEPRWY
            )
        else:
            self.dep_time.set_text(f"{self._plan.current.ADEP} --:--")
            self.dep_weather.content = "N/A"
        if not self._divert_target:
            self._show_arrival_weather(
                self._plan.current.ADES,
                self._plan.weather_des,
                self._plan.current.DESRWY,
            )

    def _show_arrival_weather(self, icao, metar, runway):
        if metar:
            self.des_time.set_text(f"{icao} {metar.time:%H:%M}")
            self._show_weather(self.des_weather, metar, runway)
        else:
            self.des_time.set_text(f"{icao} --:--")
            self.des_weather.content = "N/A"
            self.des_weather.style("color: inherit")

    def _show_weather(self, element, metar, runway):
        """METAR text led by the hazard summary, coloured by how hard it is"""
        wx = challenge(metar, [runway_heading(runway)] if runway else [])
        summary = f"{wx.icon} {wx.notes}".strip()
        # Wet runway, unless the rain icon already shows it
        if is_wet(metar) and wx.icon != HAZARD_ICONS["rain"]:
            summary = f"💧{summary}"
        element.content = f"{summary} · {weather_text(metar)}"
        element.style(f"color: {severity_colour(wx.score)}")

    def update_time(self):
        if not self._time_label:
            return
        zulu_seconds = self._plan.time
        if zulu_seconds is None:
            self._time_label.set_text("--:--:--")
            return
        hours, remain = divmod(int(zulu_seconds), 3600)
        minutes, seconds = divmod(remain, 60)
        self._time_label.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    async def select_plan(self, value):
        self._spinner.set_visibility(True)
        await self._plan.load_plan(value)
        self._spinner.set_visibility(False)
        self.update_weather()
        self.update_enroute()

        if not self._plan.current:
            return

        dep, (arr_start, app, arr_end) = plan_detail(self._plan.current)
        self._plan_dep.set_text(dep)
        self._plan_arr.set_text(arr_start)
        self._plan_arr_end.set_text(arr_end)
        # The approach carries its type, coloured from ILS (green) to manual (red)
        approach = self._generator.approach_class(
            self._plan.current.ADES, self._plan.current.APP
        )
        self._plan_app.set_text(
            f"{app} {approach.kind}" if self._plan.current.APP else approach.kind
        )
        self._plan_app.style(f"color: {approach_colour(approach.tier)}")
        self._plan_app_tip.set_text(
            approach_tip(
                self._generator.runway_approaches(self._plan.current.ADES),
                metar_wind(self.metar(self._plan.current.ADES)),
            )
        )

        self._cruise_alt.value = self._plan.cruise

        for layer in self._map_markers + self._map_lines:
            try:
                self._map.remove_layer(layer)
            except Exception:
                logger.debug("Could not remove existing layer")
        self._map_markers = []
        self._map_lines = []

        # Consecutive segments share the fix they join at, which belongs in both
        # polylines but only needs one marker
        plotted = set()
        for segment, waypoints in self._plan.current.segments:
            colour = SEGMENT_COLOURS[segment]
            icon = ICON_DIAMOND(colour)
            for waypoint in waypoints:
                if waypoint.name in plotted:
                    continue
                plotted.add(waypoint.name)
                marker = self._map.marker(
                    latlng=(waypoint.latitude, waypoint.longitude)
                )
                self._map_markers.append(marker)
                marker.run_method(":setIcon", icon)
                marker.run_method("bindTooltip", waypoint.name, TOOLTIP_OPTIONS)
            if len(waypoints) > 1:
                self._map_lines.append(
                    self._map.generic_layer(
                        name="polyline",
                        args=[
                            [(w.latitude, w.longitude) for w in waypoints],
                            {"color": colour, "weight": 2},
                        ],
                    )
                )

        self.fit_route()

        route = []
        for waypoint in self._plan.current.waypoints:
            route.append(waypoint.name)
        self._route.value = " ".join(route)

    async def move_aircraft_to_runway(self):
        runway = self._plan.current.DEPRWY
        icao_code = self._plan.current.ADEP
        if runway and icao_code:
            await self._udp.move_aircraft_to_runway(icao_code, runway)

    async def move_aircraft_to_gate(self):
        icao_code = self._plan.current.ADEP
        if icao_code:
            await self._udp.move_aircraft_to_gate(icao_code)

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


def window_size(value: str) -> str:
    """WIDTHxHEIGHT as Chrome's --window-size wants it, WIDTH,HEIGHT"""
    try:
        width, height = (int(part) for part in value.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {value!r}")
    return f"{width},{height}"


# Pending checks, kept so the event loop does not drop them
_exit_checks = set()


async def _exit_if_unused():
    await asyncio.sleep(EXIT_GRACE_S)
    if not any(client.has_socket_connection for client in Client.instances.values()):
        logger.info("Last window closed, shutting down")
        app.shutdown()


def exit_when_unused():
    """Shut the server down once no window has been connected for a while.

    The check runs as its own task rather than one tied to the client that
    left, which NiceGUI deletes after its reconnect timeout (3 s).
    """
    task = asyncio.get_running_loop().create_task(_exit_if_unused())
    _exit_checks.add(task)
    task.add_done_callback(_exit_checks.discard)


def main(reload=False, show=True):
    parser = argparse.ArgumentParser(description="X-Plane flight plan UI")
    parser.add_argument(
        "--xplane-dir",
        default=DEFAULT_XPLANE_DIR,
        help=f"X-Plane install directory (default: {DEFAULT_XPLANE_DIR})",
    )
    parser.add_argument(
        "--window-size",
        type=window_size,
        default=DEFAULT_WINDOW_SIZE,
        help=f"Size of the app window as WIDTHxHEIGHT (default: {DEFAULT_WINDOW_SIZE})",
    )
    args = parser.parse_args()
    download_missing()
    ui_inst = UI(XPlanePaths(os.path.expanduser(args.xplane_dir)))
    cmd = [
        "open",
        "-na",
        "Google Chrome",
        "--args",
        "--app=%s",
        # A fresh profile has no saved window bounds, so Chrome honours --window-size
        f"--user-data-dir=/tmp/chrome-kiosk-{uuid.uuid4()}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size={args.window_size}",
    ]
    webbrowser.register(
        "kiosk", None, webbrowser.BackgroundBrowser(cmd), preferred=True
    )
    app.add_static_files("/assets", os.path.dirname(__file__) + "/../../assets")
    app.on_startup(ui_inst.startup)
    app.on_shutdown(ui_inst.shutdown)
    # The development server restarts itself, so only exit when run normally
    if not reload:
        app.on_disconnect(exit_when_unused)
    try:
        ui.run(ui_inst.page, reload=reload, show=show)
    except (asyncio.exceptions.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown finished")


if __name__ in {"__main__", "__mp_main__"}:
    main(True, False)
