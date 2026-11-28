from contextlib import contextmanager
import logging
import math
from types import SimpleNamespace

from nicegui import run, ui

from .enroute import enroute_hazard, enroute_text, enroute_wind, route_points
from .generate import Generator, block_minutes, runway_heading, runway_score
from .route_map import RouteMap
from .weather import challenge, metar_wind

logger = logging.getLogger(__name__)

AUTO = "Auto"
# Plans judged between progress bar updates
PLAN_BATCH = 5
# Route map beside each table
MAP_WIDTH = "260px"


def hours_minutes(minutes: float) -> str:
    return f"{int(minutes) // 60}:{int(minutes) % 60:02d}"


def weather_text(wx) -> str:
    return wx.summary


def severity_colour(score: int) -> str:
    """Text colour for a weather challenge score; grey when unknown"""
    if score < 0:
        return "grey"
    if score == 0:
        return "#4caf50"
    if score <= 3:
        return "#ffc107"
    if score <= 6:
        return "#ff9800"
    return "#f44336"


# Approach tiers 1 (CAT II/III ILS) to 5 (flown by hand), green to red
APPROACH_COLOURS = {1: "#4caf50", 2: "#8bc34a", 3: "#ffc107", 4: "#ff9800", 5: "#f44336"}


def approach_colour(tier: int) -> str:
    return APPROACH_COLOURS[tier]


def approach_text(name, cls) -> str:
    """e.g. "I26 ILS CAT I", or "Visual" when there is no approach"""
    return f"{name} {cls.kind}" if name else cls.kind


def runway_wind(runway, wind) -> str:
    """Head or tailwind and crosswind on a runway, e.g. "head 10kt, cross 12kt";
    wind is (direction or None when variable, speed kt) or None"""
    if not wind:
        return ""
    direction, speed = wind
    if direction is None:
        return f"variable {speed:.0f}kt"
    angle = math.radians(direction - runway_heading(runway))
    along = speed * math.cos(angle)
    cross = abs(speed * math.sin(angle))
    text = f"{'head' if along >= 0 else 'tail'} {abs(along):.0f}kt"
    return text + (f", cross {cross:.0f}kt" if cross >= 1 else "")


def approach_tip(runway_approaches, wind=None) -> str:
    """One line per runway: its wind and every approach to it, e.g.
    "RW26 · head 15kt: R26-E RNAV, L26 LOC" """
    lines = []
    for runway, approaches in runway_approaches.items():
        on_runway = runway_wind(runway, wind)
        label = f"{runway} · {on_runway}" if on_runway else runway
        lines.append(
            f"{label}: " + ", ".join(approach_text(name, cls) for name, cls in approaches)
        )
    return "\n".join(lines)


def wind_tip(runways, wind=None) -> str:
    """One line per runway with its wind, e.g. "RW26 · head 15kt, cross 3kt" """
    return "\n".join(
        f"{runway} · {on_runway}" if (on_runway := runway_wind(runway, wind)) else runway
        for runway in runways
    )


def with_approach(score, approach_score):
    """Add the approach to a score; unknown (-1) stays so only with an ILS CAT II/III"""
    if score < 0:
        return approach_score if approach_score > 0 else -1
    return score + approach_score


def colour_weather_cells(table: ui.table, *names: str, wrap: bool = True):
    """Show each named weather cell in the colour stored as <name>_colour,
    with <name>_tip on hover; without wrap only its own line breaks split it"""
    white_space = "pre-line" if wrap else "pre"
    for name in names:
        table.add_slot(
            f"body-cell-{name}",
            f'''<q-td :props="props">
                <span :style="{{color: props.row.{name}_colour}}"
                      :title="props.row.{name}_tip" style="white-space: {white_space}">{{{{ props.value }}}}</span>
            </q-td>''',
        )


def airport_runway_cells(table: ui.table, *names: str):
    """Airport on one line and its runway in bold below, from <name> and
    <name>_runway, with <name>_tip on hovering the runway"""
    for name in names:
        table.add_slot(
            f"body-cell-{name}",
            f'''<q-td :props="props">
                <div>{{{{ props.value }}}}</div>
                <div class="text-weight-bold" style="display: inline-block">
                    {{{{ props.row.{name}_runway }}}}
                    <q-tooltip v-if="props.row.{name}_tip"
                               style="white-space: pre-line; font-size: 0.85rem">
                        {{{{ props.row.{name}_tip }}}}
                    </q-tooltip>
                </div>
            </q-td>''',
        )


def combined_score(weather, lengths):
    """Weather plus short runways; -1 when no weather is known at all."""
    known = [wx.score for wx in weather if wx.score >= 0]
    if not known:
        return -1
    return sum(known) + sum(runway_score(length) for length in lengths)


@contextmanager
def busy(*elements):
    """Spinner on buttons and a progress bar on tables while work runs"""
    for element in elements:
        element.props("loading")
    try:
        yield
    finally:
        for element in elements:
            element.props(remove="loading")


def sort_rows(rows, hardest_first):
    if hardest_first:
        return sorted(rows, key=lambda r: (-r["score"], r["minutes"]))
    return sorted(rows, key=lambda r: r["minutes"])


class PlannerDialog:
    """Existing plans on one tab, with weather and runway difficulty, and a
    generator for new plans on the other."""

    def __init__(
        self,
        generator: Generator,
        plans,
        load_plan,
        preview_plan,
        location,
        metar,
        winds,
        stations,
        on_select,
        on_generated,
    ):
        """plans() lists the FMSPlan objects, load_plan(path) awaits one with
        its procedures, preview_plan(text) awaits one from unsaved .fms text,
        location() gives the aircraft (lat, lon) or None,
        metar(icao) the latest METAR or None, winds() the WindsAloft or None,
        stations() maps METAR stations to (lat, lon),
        on_select(path) loads an existing plan and on_generated(path) runs
        after a save."""
        self._generator = generator
        self._plans = plans
        self._load_plan = load_plan
        self._plan_from_text = preview_plan
        # Generated but not yet saved
        self._generated = None
        # Cruise level the last generated route was found at, filled in for
        # reference; left as it is, the next plan picks its own level again
        self._auto_cruise = None
        self._winds = winds
        self._stations = stations
        self._location = location
        self._metar = metar
        self._on_select = on_select
        self._on_generated = on_generated
        self._plan_rows = []
        self._rows = []
        self._destination = None

        # Scrolls rather than clipping when the app window is short
        with ui.dialog() as self._dialog, ui.card().style(
            "width: 1080px; max-width: 95vw; max-height: 95vh; overflow-y: auto"
        ):
            with ui.row().classes("w-full items-center no-wrap"):
                with ui.tabs().classes("flex-1") as tabs:
                    plans_tab = ui.tab("Plans")
                    new_tab = ui.tab("New plan")
                ui.button(icon="close", on_click=self._dialog.close).props(
                    "flat round dense"
                ).tooltip("Close")
            with ui.tab_panels(tabs, value=plans_tab).classes("w-full"):
                with ui.tab_panel(plans_tab).classes("p-1"):
                    self._build_plans()
                with ui.tab_panel(new_tab).classes("p-1"):
                    self._build_generate()

    async def open(self):
        self._dialog.open()
        await self._load_plans()

    # Existing plans

    def _build_plans(self):
        with ui.row().classes("w-full items-center"):
            self._plans_hardest_first = ui.switch(
                "Hardest first (weather, runways and approach)",
                on_change=self._show_plans,
            )
            self._plans_refresh = ui.button(icon="refresh", on_click=self._load_plans)
            self._plans_refresh.tooltip("Reload plans and weather")
        # Filled as the plans are read and judged
        self._plans_progress = ui.linear_progress(value=0, show_value=False).classes(
            "w-full"
        )
        self._plans_progress_label = ui.label("").classes("text-xs")
        self._plans_progress.set_visibility(False)
        self._plans_progress_label.set_visibility(False)
        with ui.row().classes("w-full no-wrap gap-2"):
            self._build_plans_table()
            self._plans_map = RouteMap()
            self._plans_map.leaflet.style(f"width: {MAP_WIDTH}; height: 320px")

    def _build_plans_table(self):
        self._plans_table = ui.table(
            columns=[
                {"name": "dep", "label": "From", "field": "dep", "align": "left",
                 "style": "white-space: pre-line",
                 "sortable": True},
                {"name": "arr", "label": "To", "field": "arr", "align": "left",
                 "style": "white-space: pre-line",
                 "sortable": True},
                {"name": "nm", "label": "nm", "field": "nm", "sortable": True},
                {"name": "time", "label": "Block", "field": "time", "sortable": True},
                {"name": "dep_wx", "label": "Dep weather", "field": "dep_wx",
                 "align": "left"},
                {"name": "arr_wx", "label": "Arr weather", "field": "arr_wx",
                 "align": "left"},
                {"name": "enroute", "label": "Enroute", "field": "enroute",
                 "align": "left"},
                {"name": "app", "label": "Approach", "field": "app", "align": "left",
                 "sortable": True},
                {"name": "dep_rwy", "label": "Dep rwy ft", "field": "dep_rwy",
                 "sortable": True},
                {"name": "arr_rwy", "label": "Arr rwy ft", "field": "arr_rwy",
                 "sortable": True},
            ],
            rows=[],
            row_key="path",
            selection="single",
            on_select=self._select_plan,
        ).props("dense virtual-scroll").classes("flex-1 min-w-0").style("height: 320px")
        colour_weather_cells(self._plans_table, "dep_wx", "arr_wx", "app")
        airport_runway_cells(self._plans_table, "dep", "arr")
        colour_weather_cells(self._plans_table, "enroute", wrap=False)
        # Clicking a row shows its route on the map; the checkbox loads it
        self._plans_table.on("row-click", self._preview_plan)

    def _plan_row(self, plan, winds, stations):
        """Table row for an existing plan, judged on its planned runways and
        the weather along its route."""
        lengths, weather = [], []
        for icao, runway in ((plan.ADEP, plan.DEPRWY), (plan.ADES, plan.DESRWY)):
            headings = [runway_heading(runway)] if runway else []
            weather.append(challenge(self._metar(icao), headings))
            lengths.append(self._generator.runway_length_ft(icao, runway))
        points = route_points(plan.waypoints)
        wind = enroute_wind(points, winds) if winds else None
        hazard = enroute_hazard(points, stations, self._metar)
        enroute_score = hazard.challenge.score if hazard else 0
        approach = self._generator.approach_class(plan.ADES, plan.APP)
        distance = self._generator.distance_nm(plan.ADEP, plan.ADES)
        minutes = block_minutes(distance) if distance else 0
        return {
            "path": plan.file_path,
            # The runway on a line of its own keeps the column narrow
            "dep": f"{plan.departure_board} ({plan.ADEP})",
            "dep_runway": plan.DEPRWY or "",
            "dep_tip": wind_tip(
                self._generator.runway_approaches(plan.ADEP),
                metar_wind(self._metar(plan.ADEP)),
            ),
            "arr": f"{plan.destination_board} ({plan.ADES})",
            "arr_runway": plan.DESRWY or "",
            "arr_tip": wind_tip(
                self._generator.runway_approaches(plan.ADES),
                metar_wind(self._metar(plan.ADES)),
            ),
            "nm": round(distance) if distance else "",
            "time": hours_minutes(minutes) if distance else "",
            "minutes": minutes,
            "dep_wx": weather_text(weather[0]),
            "dep_wx_colour": severity_colour(weather[0].score),
            "arr_wx": weather_text(weather[1]),
            "arr_wx_colour": severity_colour(weather[1].score),
            # Short lines of their own: wind, its maximum, then any hazard
            "enroute": enroute_text(wind, hazard)
            .replace(" · ", "\n")
            .replace(", max ", "\nmax "),
            "enroute_colour": severity_colour(enroute_score),
            "app": approach_text(plan.APP, approach),
            "app_colour": approach_colour(approach.tier),
            "app_tip": approach_tip(
                self._generator.runway_approaches(plan.ADES),
                metar_wind(self._metar(plan.ADES)),
            ),
            "dep_rwy": lengths[0] or "",
            "arr_rwy": lengths[1] or "",
            "score": with_approach(
                self._route_score(combined_score(weather, lengths), enroute_score),
                approach.score,
            ),
        }

    @staticmethod
    def _route_score(ends_score, enroute_score):
        """Ends plus enroute; a hazard on the route counts without end weather"""
        if ends_score < 0:
            return enroute_score if enroute_score > 0 else -1
        return ends_score + enroute_score

    async def _load_plans(self):
        def setup():
            # Reading the plan folder and the weather is slow, keep it off the UI
            return self._plans(), self._winds(), self._stations()

        def progress(done, total, text):
            self._plans_progress.set_value(done / total if total else 0)
            self._plans_progress_label.set_text(text)

        for element in (self._plans_progress, self._plans_progress_label):
            element.set_visibility(True)
        progress(0, 1, "Reading plans...")
        rows = []
        try:
            with busy(self._plans_table, self._plans_refresh):
                plans, winds, stations = await run.io_bound(setup)
                # Small batches so the bar moves while the rows are worked out
                for start in range(0, len(plans), PLAN_BATCH):
                    batch = plans[start : start + PLAN_BATCH]
                    rows += await run.io_bound(
                        lambda batch=batch: [
                            self._plan_row(plan, winds, stations) for plan in batch
                        ]
                    )
                    progress(len(rows), len(plans), f"{len(rows)} / {len(plans)} plans")
        finally:
            for element in (self._plans_progress, self._plans_progress_label):
                element.set_visibility(False)
        self._plan_rows = rows
        self._show_plans()

    def _show_plans(self):
        self._plans_table.rows = sort_rows(
            self._plan_rows, self._plans_hardest_first.value
        )
        self._plans_table.selected = []
        self._plans_table.update()

    async def _preview_plan(self, e):
        path = e.args[1]["path"]
        plan = await self._load_plan(path)
        if plan:
            self._plans_map.show(plan.segments)

    def _select_plan(self, e):
        if not e.selection:
            return
        self._dialog.close()
        self._on_select(e.selection[0]["path"])

    # New plan

    def _build_generate(self):
        with ui.row().classes("w-full items-center no-wrap"):
            # Searchable by city, IATA, ICAO or airport name
            self._departure = (
                ui.select(
                    self._generator.airport_choices(),
                    label="Departure",
                    with_input=True,
                    on_change=self._departure_changed,
                )
                .props("dense")
                .style("min-width: 280px")
            )
            # Optional; when set Find shows just this airport, ready to generate
            self._arrival = (
                ui.select(
                    self._generator.airport_choices(),
                    label="Destination (optional)",
                    with_input=True,
                    clearable=True,
                    on_change=self._preselect,
                )
                .props("dense")
                .style("min-width: 280px")
            )
            here = ui.button(icon="my_location", on_click=self._use_location)
            here.tooltip("Nearest airport to the aircraft")
            with ui.column().classes("flex-1 gap-0"):
                self._range_label = ui.label()
                self._range = ui.range(
                    min=30,
                    max=180,
                    step=5,
                    value={"min": 60, "max": 90},
                    on_change=self._update_range_label,
                )
            self._find_button = ui.button("Find", on_click=self._find)
        self._update_range_label()
        self._bad_weather_first = ui.switch(
            "Hardest first (weather, runways and approach)", on_change=self._show_rows
        )

        # The map spans the table and the plan options beside it
        with ui.row().classes("w-full no-wrap gap-2 items-stretch"):
            with ui.column().classes("flex-1 min-w-0 gap-2"):
                self._build_destinations_table()
                self._build_plan_options()
            self._new_map = RouteMap()
            self._new_map.leaflet.style(
                f"width: {MAP_WIDTH}; height: auto; min-height: 200px"
            )
        self._summary = ui.label().classes("text-sm")

    def _build_destinations_table(self):
        self._table = ui.table(
            columns=[
                {"name": "iata", "label": "IATA", "field": "iata", "align": "left",
                 "sortable": True},
                {"name": "city", "label": "City", "field": "city", "align": "left",
                 "sortable": True},
                {"name": "icao", "label": "ICAO", "field": "icao", "align": "left",
                 "sortable": True},
                {"name": "nm", "label": "nm", "field": "nm", "sortable": True},
                {"name": "time", "label": "Block", "field": "time", "sortable": True},
                {"name": "rwy", "label": "Rwy ft", "field": "rwy", "sortable": True},
                {"name": "wx", "label": "Weather", "field": "wx", "align": "left"},
                {"name": "app", "label": "Approach", "field": "app", "align": "left",
                 "sortable": True},
                {"name": "known", "label": "Plans", "field": "known"},
            ],
            rows=[],
            row_key="icao",
            selection="single",
            on_select=self._select_destination,
        ).props("dense virtual-scroll").classes("w-full").style("height: 200px")
        colour_weather_cells(self._table, "wx", "app")

    def _build_plan_options(self):
        with ui.row().classes("w-full no-wrap items-stretch gap-4"):
            self._build_plan_selects()
            self._generate_button = ui.button(icon="route", on_click=self._generate)
            self._generate_button.tooltip("Generate a route to preview")
            self._generate_button.disable()
            self._save_button = ui.button(icon="save", on_click=self._save)
            self._save_button.tooltip("Save the plan")
            self._save_button.disable()

    def _build_plan_selects(self):
        # Equal columns, each field filling its own, so no label is clipped
        with ui.grid(columns=4).classes("flex-1 min-w-0 gap-4"):
            self._dep_rwy = ui.select(
                [AUTO],
                label="Departure runway",
                value=AUTO,
                on_change=self._clear_generated,
            ).classes("w-full")
            self._des_rwy = ui.select(
                [AUTO],
                label="Arrival runway",
                value=AUTO,
                on_change=self._load_approaches,
            ).classes("w-full")
            self._approach = ui.select(
                [AUTO], label="Approach", value=AUTO, on_change=self._clear_generated
            ).classes("w-full")
            self._cruise = ui.input(
                "Cruise",
                placeholder="auto",
                prefix="FL",
                on_change=self._cruise_changed,
            ).classes("w-full")

    def _clear_generated(self):
        """Drop an unsaved plan once what it was generated from changes"""
        if self._generated is None:
            return
        self._generated = None
        self._save_button.disable()
        self._summary.set_text("")
        self._show_route()

    def _cruise_changed(self):
        # Filling in the found level is not a change to the plan
        if (self._cruise.value or "").strip() != self._auto_cruise:
            self._clear_generated()

    async def _departure_changed(self):
        self._clear_generated()
        self._show_route()
        adep = (self._departure.value or "").strip().upper()
        if adep:
            await self._load_runways(self._dep_rwy, adep, arrival=False)
        else:
            self._dep_rwy.set_options([AUTO], value=AUTO)

    def _show_route(self):
        """Departure and the chosen destination joined by a straight line"""
        adep = (self._departure.value or "").strip().upper()
        icaos = [icao for icao in (adep, self._destination) if icao]
        positions = self._generator.positions(icaos)
        points = [
            SimpleNamespace(name=icao, latitude=lat, longitude=lon)
            for icao in icaos
            if icao in positions
            for lat, lon in [positions[icao]]
        ]
        self._new_map.show([("ENRT", points)] if points else [])

    def _update_range_label(self):
        value = self._range.value
        self._range_label.set_text(
            f"Block time {hours_minutes(value['min'])} - {hours_minutes(value['max'])}"
        )

    def _challenge(self, icao):
        """Weather challenge, longest runway length, the planned approach and
        what each runway offers, for a destination."""
        runways = self._generator.runways(icao)
        metar = self._metar(icao)
        wx = challenge(metar, [runway_heading(rw) for rw in runways])
        planned = self._generator.planned_approach(icao, metar_wind(metar))
        others = approach_tip(self._generator.runway_approaches(icao), metar_wind(metar))
        return wx, self._generator.longest_runway_ft(icao), planned, others

    def _show_rows(self):
        self._table.rows = sort_rows(self._rows, self._bad_weather_first.value)
        self._table.selected = []
        self._table.update()

    def _use_location(self):
        location = self._location()
        if location is None:
            ui.notify("No aircraft position from the sim", type="warning")
            return
        icao = self._generator.nearest_airport(*location)
        if icao:
            self._departure.value = icao

    async def _preselect(self):
        if self._departure.value:
            await self._find()

    async def _find(self):
        adep = (self._departure.value or "").strip().upper()
        ades = (self._arrival.value or "").strip().upper() or None
        value = self._range.value

        def search():
            found = self._generator.destinations(
                adep, value["min"], value["max"], only=ades
            )
            return found, [self._challenge(d.icao) for d in found]

        with busy(self._table, self._find_button):
            try:
                found, weather = await run.io_bound(search)
            except KeyError as e:
                ui.notify(str(e), type="negative")
                return
        self._rows = [
            {
                "icao": d.icao,
                "iata": d.iata,
                "city": d.city,
                "nm": round(d.distance),
                "time": hours_minutes(d.minutes),
                "minutes": d.minutes,
                "rwy": length or "",
                "wx": weather_text(wx),
                "wx_colour": severity_colour(wx.score),
                "app": f"{runway} {approach_text(name, cls)}" if runway else cls.kind,
                "app_colour": approach_colour(cls.tier),
                "app_tip": others,
                "score": with_approach(combined_score([wx], [length]), cls.score),
                "known": "✈" if d.known else "",
            }
            for d, (wx, length, (runway, name, cls), others) in zip(found, weather)
        ]
        self._show_rows()
        self._destination = None
        self._clear_generated()
        self._show_route()
        self._generate_button.disable()
        # A chosen destination is selected straight away, ready to generate
        if ades and self._rows:
            self._table.selected = [self._rows[0]]
            self._table.update()
            await self._select_destination(SimpleNamespace(selection=[self._rows[0]]))

    async def _select_destination(self, e):
        selected = e.selection[0]["icao"] if e.selection else None
        self._destination = selected
        self._clear_generated()
        self._show_route()
        self._summary.set_text("")
        if not selected:
            self._generate_button.disable()
            return
        await self._load_runways(self._des_rwy, selected, arrival=True)
        self._generate_button.enable()

    async def _load_runways(self, select: ui.select, icao: str, arrival: bool):
        """Offer the airport's runways, defaulting to the one picked for the wind."""
        wind = metar_wind(self._metar(icao))
        runways, default = await run.io_bound(
            lambda: (
                self._generator.runways(icao),
                self._generator.default_runway(icao, arrival, wind),
            )
        )
        # Each runway with its length, surface and wind, e.g.
        # "RW26 9800ft asphalt (head 10kt, cross 12kt)"
        options = {AUTO: AUTO}
        for runway in runways:
            parts = [runway]
            length = self._generator.runway_length_ft(icao, runway)
            if length:
                parts.append(f"{length}ft")
            surface = self._generator.runway_surface(icao, runway)
            if surface:
                parts.append(surface)
            on_runway = runway_wind(runway, wind)
            if on_runway:
                parts.append(f"({on_runway})")
            options[runway] = " ".join(parts)
        select.set_options(options, value=default or AUTO)

    async def _load_approaches(self):
        self._clear_generated()
        icao, runway = self._destination, self._des_rwy.value
        if not icao or runway in (None, AUTO):
            self._approach.set_options([AUTO], value=AUTO)
            return
        approaches = await run.io_bound(self._generator.approaches, icao, runway)
        # The first approach is the preferred one, which Auto also picks
        options = {AUTO: AUTO}
        for name in approaches:
            options[name] = f"{name} – {self._generator.approach_class(icao, name).kind}"
        self._approach.set_options(options, value=AUTO)

    async def _generate(self):
        adep = (self._departure.value or "").strip().upper()
        ades = self._destination
        if not adep or not ades:
            return
        if self._generator.plan_exists(adep, ades):
            ui.notify(f"{adep}-{ades} already exists", type="negative")
            return
        cruise = (self._cruise.value or "").strip()
        if cruise == self._auto_cruise:
            cruise = ""
        if cruise and not cruise.isdigit():
            ui.notify("Cruise must be a flight level such as 240", type="negative")
            return

        def pick(select: ui.select):
            return None if select.value == AUTO else select.value

        self._clear_generated()
        self._summary.set_text("Planning...")
        try:
            with busy(self._generate_button):
                plan = await run.io_bound(
                    self._generator.plan,
                    adep,
                    ades,
                    pick(self._dep_rwy),
                    pick(self._des_rwy),
                    int(cruise) if cruise else None,
                    pick(self._approach),
                )
                preview = await self._plan_from_text(plan.text)
        except (KeyError, ValueError, RuntimeError) as e:
            self._summary.set_text("")
            ui.notify(str(e), type="negative")
            return
        finally:
            self._generate_button.enable()

        logger.info(f"Generated {plan.summary}")
        self._summary.set_text(plan.summary)
        self._new_map.show(preview.segments)
        if not cruise:
            self._auto_cruise = str(plan.cruise_fl)
            self._cruise.value = self._auto_cruise
        self._generated = plan
        self._save_button.enable()

    async def _save(self):
        plan = self._generated
        if plan is None:
            return
        try:
            path = self._generator.write(plan)
        except FileExistsError:
            ui.notify(f"{plan.adep}-{plan.ades} already exists", type="negative")
            return
        self._generated = None
        self._save_button.disable()
        ui.notify(f"Saved {plan.adep}-{plan.ades}", type="positive")
        self._on_generated(path)
        await self._load_plans()
