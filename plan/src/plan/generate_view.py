from contextlib import contextmanager
import logging

from nicegui import run, ui

from .generate import Generator, block_minutes, runway_heading, runway_score
from .weather import challenge, metar_wind

logger = logging.getLogger(__name__)

AUTO = "Auto"


def hours_minutes(minutes: float) -> str:
    return f"{int(minutes) // 60}:{int(minutes) % 60:02d}"


def weather_text(wx) -> str:
    return f"{wx.icon} {wx.notes}".strip()


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


def colour_weather_cells(table: ui.table, *names: str):
    """Show each named weather cell in the colour stored as <name>_colour."""
    for name in names:
        table.add_slot(
            f"body-cell-{name}",
            f'''<q-td :props="props">
                <span :style="{{color: props.row.{name}_colour}}">{{{{ props.value }}}}</span>
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
        self, generator: Generator, plans, location, metar, on_select, on_generated
    ):
        """plans() lists the FMSPlan objects, location() gives the aircraft
        (lat, lon) or None, metar(icao) the latest METAR or None, on_select(path)
        loads an existing plan and on_generated(path) runs after a save."""
        self._generator = generator
        self._plans = plans
        self._location = location
        self._metar = metar
        self._on_select = on_select
        self._on_generated = on_generated
        self._plan_rows = []
        self._rows = []
        self._destination = None

        # Scrolls rather than clipping when the app window is short
        with ui.dialog() as self._dialog, ui.card().style(
            "min-width: 820px; max-width: 95vw; max-height: 95vh; overflow-y: auto"
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
                "Hardest first (weather and short runways)",
                on_change=self._show_plans,
            )
            self._plans_refresh = ui.button(icon="refresh", on_click=self._load_plans)
            self._plans_refresh.tooltip("Reload plans and weather")
        self._plans_table = ui.table(
            columns=[
                {"name": "dep", "label": "From", "field": "dep", "align": "left",
                 "sortable": True},
                {"name": "arr", "label": "To", "field": "arr", "align": "left",
                 "sortable": True},
                {"name": "nm", "label": "nm", "field": "nm", "sortable": True},
                {"name": "time", "label": "Block", "field": "time", "sortable": True},
                {"name": "dep_wx", "label": "Dep weather", "field": "dep_wx",
                 "align": "left"},
                {"name": "arr_wx", "label": "Arr weather", "field": "arr_wx",
                 "align": "left"},
                {"name": "dep_rwy", "label": "Dep rwy ft", "field": "dep_rwy",
                 "sortable": True},
                {"name": "arr_rwy", "label": "Arr rwy ft", "field": "arr_rwy",
                 "sortable": True},
            ],
            rows=[],
            row_key="path",
            selection="single",
            on_select=self._select_plan,
        ).props("dense virtual-scroll").style("height: 320px")
        colour_weather_cells(self._plans_table, "dep_wx", "arr_wx")

    def _plan_row(self, plan):
        """Table row for an existing plan, judged on its planned runways."""
        lengths, weather = [], []
        for icao, runway in ((plan.ADEP, plan.DEPRWY), (plan.ADES, plan.DESRWY)):
            headings = [runway_heading(runway)] if runway else []
            weather.append(challenge(self._metar(icao), headings))
            lengths.append(self._generator.runway_length_ft(icao, runway))
        distance = self._generator.distance_nm(plan.ADEP, plan.ADES)
        minutes = block_minutes(distance) if distance else 0
        return {
            "path": plan.file_path,
            "dep": f"{plan.departure_board} ({plan.ADEP}) {plan.DEPRWY or ''}",
            "arr": f"{plan.destination_board} ({plan.ADES}) {plan.DESRWY or ''}",
            "nm": round(distance) if distance else "",
            "time": hours_minutes(minutes) if distance else "",
            "minutes": minutes,
            "dep_wx": weather_text(weather[0]),
            "dep_wx_colour": severity_colour(weather[0].score),
            "arr_wx": weather_text(weather[1]),
            "arr_wx_colour": severity_colour(weather[1].score),
            "dep_rwy": lengths[0] or "",
            "arr_rwy": lengths[1] or "",
            "score": combined_score(weather, lengths),
        }

    async def _load_plans(self):
        def rows():
            # Reading the plan folder and the weather is slow, keep it off the UI
            return [self._plan_row(plan) for plan in self._plans()]

        with busy(self._plans_table, self._plans_refresh):
            self._plan_rows = await run.io_bound(rows)
        self._show_plans()

    def _show_plans(self):
        self._plans_table.rows = sort_rows(
            self._plan_rows, self._plans_hardest_first.value
        )
        self._plans_table.selected = []
        self._plans_table.update()

    def _select_plan(self, e):
        if not e.selection:
            return
        self._dialog.close()
        self._on_select(e.selection[0]["path"])

    # New plan

    def _build_generate(self):
        with ui.row().classes("w-full items-center no-wrap"):
            self._departure = ui.input("Departure", placeholder="ICAO").props("dense")
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
            "Hardest first (weather and short runways)", on_change=self._show_rows
        )

        self._table = ui.table(
            columns=[
                {"name": "iata", "label": "", "field": "iata", "align": "left"},
                {"name": "city", "label": "City", "field": "city", "align": "left"},
                {"name": "icao", "label": "ICAO", "field": "icao", "align": "left"},
                {"name": "nm", "label": "nm", "field": "nm", "sortable": True},
                {"name": "time", "label": "Block", "field": "time", "sortable": True},
                {"name": "rwy", "label": "Rwy ft", "field": "rwy", "sortable": True},
                {"name": "wx", "label": "Weather", "field": "wx", "align": "left"},
                {"name": "known", "label": "Plans", "field": "known"},
            ],
            rows=[],
            row_key="icao",
            selection="single",
            on_select=self._select_destination,
        ).props("dense virtual-scroll").style("height: 160px")
        colour_weather_cells(self._table, "wx")

        # Equal columns, each field filling its own, so no label is clipped
        with ui.grid(columns=4).classes("w-full gap-4"):
            self._dep_rwy = ui.select(
                [AUTO], label="Departure runway", value=AUTO
            ).classes("w-full")
            self._des_rwy = ui.select(
                [AUTO],
                label="Arrival runway",
                value=AUTO,
                on_change=self._load_approaches,
            ).classes("w-full")
            self._approach = ui.select(
                [AUTO], label="Approach", value=AUTO
            ).classes("w-full")
            self._cruise = ui.input(
                "Cruise", placeholder="auto", prefix="FL"
            ).classes("w-full")
        self._summary = ui.label().classes("text-sm")
        self._generate_button = ui.button("Generate", on_click=self._generate)
        self._generate_button.disable()

    def _update_range_label(self):
        value = self._range.value
        self._range_label.set_text(
            f"Block time {hours_minutes(value['min'])} - {hours_minutes(value['max'])}"
        )

    def _challenge(self, icao):
        """Weather challenge and the longest runway length for a destination."""
        runways = self._generator.runways(icao)
        wx = challenge(self._metar(icao), [runway_heading(rw) for rw in runways])
        return wx, self._generator.longest_runway_ft(icao)

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

    async def _find(self):
        adep = (self._departure.value or "").strip().upper()
        value = self._range.value

        def search():
            found = self._generator.destinations(adep, value["min"], value["max"])
            return found, [self._challenge(d.icao) for d in found]

        with busy(self._table, self._find_button):
            try:
                found, weather = await run.io_bound(search)
            except KeyError as e:
                ui.notify(str(e), type="negative")
                return
            # Runways for the departure load the navdata, which then stays cached
            await self._load_runways(self._dep_rwy, adep, arrival=False)
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
                "score": combined_score([wx], [length]),
                "known": "✈" if d.known else "",
            }
            for d, (wx, length) in zip(found, weather)
        ]
        self._show_rows()
        self._destination = None
        self._generate_button.disable()

    async def _select_destination(self, e):
        selected = e.selection[0]["icao"] if e.selection else None
        self._destination = selected
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
        select.set_options([AUTO] + runways, value=default or AUTO)

    async def _load_approaches(self):
        icao, runway = self._destination, self._des_rwy.value
        if not icao or runway in (None, AUTO):
            self._approach.set_options([AUTO], value=AUTO)
            return
        approaches = await run.io_bound(self._generator.approaches, icao, runway)
        # The first approach is the preferred one, which Auto also picks
        self._approach.set_options([AUTO] + approaches, value=AUTO)

    async def _generate(self):
        adep = (self._departure.value or "").strip().upper()
        ades = self._destination
        if not adep or not ades:
            return
        if self._generator.plan_exists(adep, ades):
            ui.notify(f"{adep}-{ades} already exists", type="negative")
            return
        cruise = (self._cruise.value or "").strip()
        if cruise and not cruise.isdigit():
            ui.notify("Cruise must be a flight level such as 240", type="negative")
            return

        def pick(select: ui.select):
            return None if select.value == AUTO else select.value

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
            path = self._generator.write(plan)
        except FileExistsError:
            self._summary.set_text("")
            ui.notify(f"{adep}-{ades} already exists", type="negative")
            return
        except (KeyError, ValueError, RuntimeError) as e:
            self._summary.set_text("")
            ui.notify(str(e), type="negative")
            return
        finally:
            self._generate_button.enable()

        logger.info(f"Generated {plan.summary}")
        self._summary.set_text(plan.summary)
        ui.notify(f"Saved {adep}-{ades}", type="positive")
        self._on_generated(path)
        await self._load_plans()
