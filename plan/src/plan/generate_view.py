import logging

from nicegui import run, ui

from .generate import Generator, runway_heading, runway_score
from .weather import challenge, metar_wind

logger = logging.getLogger(__name__)

AUTO = "Auto"


def hours_minutes(minutes: float) -> str:
    return f"{int(minutes) // 60}:{int(minutes) % 60:02d}"


class GenerateDialog:
    """Pick a departure, a destination within a block time range, then
    runways and approach, and save a new plan to the sim's plan folder."""

    def __init__(self, generator: Generator, location, metar, on_generated):
        """location() gives the aircraft (lat, lon) or None, metar(icao) the
        latest METAR or None, on_generated(path) runs after a save."""
        self._generator = generator
        self._location = location
        self._metar = metar
        self._rows = []
        self._on_generated = on_generated
        self._destination = None

        with ui.dialog() as self._dialog, ui.card().style("min-width: 620px"):
            ui.label("New flight plan").classes("text-lg")
            with ui.row().classes("w-full items-center no-wrap"):
                self._departure = ui.input(
                    "Departure", placeholder="ICAO"
                ).props("dense")
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
                    {"name": "wx_icon", "label": "", "field": "wx_icon"},
                    {"name": "wx", "label": "Weather", "field": "wx", "align": "left"},
                    {"name": "known", "label": "Plans", "field": "known"},
                ],
                rows=[],
                row_key="icao",
                selection="single",
                on_select=self._select_destination,
            ).props("dense virtual-scroll").style("height: 260px")

            with ui.row().classes("w-full no-wrap"):
                self._dep_rwy = ui.select([AUTO], label="Dep runway", value=AUTO)
                self._des_rwy = ui.select(
                    [AUTO], label="Arr runway", value=AUTO, on_change=self._load_approaches
                )
                self._approach = ui.select([AUTO], label="Approach", value=AUTO)
                self._cruise = ui.input("Cruise", placeholder="auto", prefix="FL")
            self._summary = ui.label().classes("text-sm")
            with ui.row():
                self._generate_button = ui.button("Generate", on_click=self._generate)
                self._generate_button.disable()
                ui.button("Close", on_click=self._dialog.close)

    def open(self):
        self._dialog.open()

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
        if self._bad_weather_first.value:
            rows = sorted(self._rows, key=lambda r: (-r["score"], r["minutes"]))
        else:
            rows = sorted(self._rows, key=lambda r: r["minutes"])
        self._table.rows = rows
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
        try:
            found = self._generator.destinations(adep, value["min"], value["max"])
        except KeyError as e:
            ui.notify(str(e), type="negative")
            return
        self._find_button.disable()
        try:
            weather = await run.io_bound(
                lambda: [self._challenge(d.icao) for d in found]
            )
        finally:
            self._find_button.enable()
        self._rows = [
            {
                "icao": d.icao,
                "iata": d.iata,
                "city": d.city,
                "nm": round(d.distance),
                "time": hours_minutes(d.minutes),
                "minutes": d.minutes,
                "rwy": length or "",
                "wx_icon": wx.icon,
                "wx": wx.notes,
                # Unknown weather keeps its -1 so it still sorts below calm
                "score": wx.score + (runway_score(length) if wx.score >= 0 else 0),
                "known": "✈" if d.known else "",
            }
            for d, (wx, length) in zip(found, weather)
        ]
        self._show_rows()
        self._destination = None
        self._generate_button.disable()
        # Runways for the departure load the navdata, which then stays cached
        await self._load_runways(self._dep_rwy, adep, arrival=False)

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

        self._generate_button.disable()
        self._summary.set_text("Planning...")
        try:
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
