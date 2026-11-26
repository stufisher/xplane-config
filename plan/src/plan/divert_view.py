from types import SimpleNamespace

from nicegui import run, ui

from .divert import Divert, RunwayEnd, autobrake
from .generate_view import (
    approach_colour,
    approach_text,
    busy,
    colour_weather_cells,
    runway_wind,
    severity_colour,
)
from .weather import challenge, is_wet, metar_wind

M_TO_FT = 3.28084
BRAKE_COLOURS = {"LO": "#4caf50", "MED": "#ff9800", "": "#f44336"}
MS_TO_KT = 1.943844
# Minutes added to the direct flight time for joining final and flying it
APPROACH_MINUTES = 3


def ils_text(runway: RunwayEnd) -> str:
    """e.g. "ILS ISW 108.70 CRS 224 GS 3.0" """
    ils = runway.ils
    if not ils:
        return ""
    glide = f" GS {ils.glideslope:.1f}" if ils.glideslope else ""
    kind = "ILS" if ils.glideslope else "LOC"
    return f"{kind} {ils.ident} {ils.frequency:.2f} CRS {ils.course_mag:03.0f}{glide}"


class DivertDialog:
    """Airports near the aircraft, or any found by search; then a runway,
    which on_divert(icao, label, runway) turns into vectors on the main page."""

    def __init__(self, divert: Divert, generator, location, metar, speeds, on_divert):
        """location() gives the sim Location, metar(icao) the latest METAR or
        None, speeds(wind, runway) the approach Speeds, on_divert(icao, label,
        runway) starts guidance to a runway."""
        self._divert = divert
        self._speeds = speeds
        self._generator = generator
        self._location = location
        self._metar = metar
        self._on_divert = on_divert
        self._airport = None
        self._runways = []

        with ui.dialog() as self._dialog, ui.card().style(
            "min-width: 820px; max-width: 95vw; max-height: 95vh; overflow-y: auto"
        ):
            with ui.row().classes("w-full items-center no-wrap"):
                ui.label("Divert").classes("text-lg")
                self._search = (
                    ui.select(
                        divert.choices(),
                        label="Search airport",
                        with_input=True,
                        clearable=True,
                        on_change=self._search_airport,
                    )
                    .props("dense")
                    .classes("flex-1")
                )
                self._refresh = ui.button(icon="my_location", on_click=self._load_nearby)
                self._refresh.tooltip("Airports nearest the aircraft")
                ui.button(icon="close", on_click=self._dialog.close).props(
                    "flat round dense"
                ).tooltip("Close")

            self._airports_table = ui.table(
                columns=[
                    {"name": "iata", "label": "IATA", "field": "iata", "align": "left",
                     "sortable": True},
                    {"name": "city", "label": "City", "field": "city", "align": "left",
                     "sortable": True},
                    {"name": "icao", "label": "ICAO", "field": "icao", "align": "left"},
                    {"name": "name", "label": "Name", "field": "name", "align": "left"},
                    {"name": "nm", "label": "nm", "field": "nm", "sortable": True},
                    {"name": "brg", "label": "Brg", "field": "brg"},
                    {"name": "eta", "label": "ETA min", "field": "eta", "sortable": True},
                    {"name": "rwy", "label": "Rwy ft", "field": "rwy", "sortable": True},
                    {"name": "wx", "label": "Weather", "field": "wx", "align": "left"},
                    {"name": "reach", "label": "Reach", "field": "reach", "align": "left"},
                ],
                rows=[],
                row_key="icao",
                selection="single",
                on_select=self._select_airport,
            ).props("dense virtual-scroll").classes("w-full").style("height: 200px")
            colour_weather_cells(self._airports_table, "wx", "reach")

            self._airport_label = ui.label("").classes("text-sm")
            self._runways_table = ui.table(
                columns=[
                    {"name": "rwy", "label": "Runway", "field": "rwy", "align": "left"},
                    {"name": "length", "label": "Length ft", "field": "length",
                     "sortable": True},
                    {"name": "hdg", "label": "Hdg", "field": "hdg"},
                    {"name": "wind", "label": "Wind", "field": "wind", "align": "left"},
                    {"name": "brake", "label": "Brake", "field": "brake",
                     "align": "left"},
                    {"name": "ils", "label": "ILS", "field": "ils", "align": "left"},
                    {"name": "app", "label": "Approaches", "field": "app",
                     "align": "left"},
                ],
                rows=[],
                row_key="rwy",
                selection="single",
                on_select=self._select_runway,
            ).props("dense").classes("w-full")
            colour_weather_cells(self._runways_table, "app", "brake")

    async def open(self):
        self._dialog.open()
        if not self._airports_table.rows:
            await self._load_nearby()

    def _aircraft(self):
        """(lat, lon, altitude ft, variation) or None without a position"""
        loc = self._location()
        if loc is None or loc.latitude is None:
            return None
        return loc.latitude, loc.longitude, loc.altitude_ft, loc.variation

    def _speed(self):
        """Ground speed, kt, 0 without one"""
        loc = self._location()
        return (loc.groundspeed or 0) * MS_TO_KT if loc else 0

    def _eta(self, distance):
        """Minutes to an airport at the current ground speed, "" when slow"""
        speed = self._speed()
        if speed < 50:
            return ""
        return round(distance / speed * 60 + APPROACH_MINUTES)

    def _row(self, airport, variation):
        metar = self._metar(airport.icao)
        wx = challenge(metar, [])
        if airport.too_high_nm:
            reach, reach_colour = f"too high, +{airport.too_high_nm:.0f}nm", "#f44336"
        else:
            reach, reach_colour = "ok", "#4caf50"
        return {
            "icao": airport.icao,
            "iata": airport.iata,
            "city": airport.city,
            "name": airport.name,
            "nm": round(airport.distance),
            "brg": f"{(airport.bearing_true + variation) % 360:03.0f}",
            "eta": self._eta(airport.distance),
            "rwy": self._generator.longest_runway_ft(airport.icao) or "",
            "wx": f"{wx.icon} {wx.notes}".strip(),
            "wx_colour": severity_colour(wx.score),
            "reach": reach,
            "reach_colour": reach_colour,
        }

    async def _load_nearby(self):
        aircraft = self._aircraft()
        if aircraft is None:
            ui.notify("No aircraft position from the sim", type="warning")
            return
        lat, lon, altitude, variation = aircraft
        speed = self._speed() or None

        def rows():
            return [
                self._row(a, variation)
                for a in self._divert.nearby(lat, lon, altitude, speed)
            ]

        with busy(self._airports_table, self._refresh):
            self._airports_table.rows = await run.io_bound(rows)
        self._airports_table.selected = []
        self._airports_table.update()

    async def _search_airport(self, e):
        if not e.value:
            return
        aircraft = self._aircraft()
        lat, lon, altitude, variation = aircraft if aircraft else (0, 0, 0, 0)
        airport = self._divert.airport(
            e.value, lat, lon, altitude, self._speed() or None
        )
        if airport is None:
            return
        row = await run.io_bound(self._row, airport, variation)
        self._airports_table.rows = [row]
        self._airports_table.selected = [row]
        self._airports_table.update()
        await self._select_airport(SimpleNamespace(selection=[row]))

    async def _select_airport(self, e):
        if not e.selection:
            return
        row = e.selection[0]
        self._airport = row
        icao = row["icao"]
        variation = (self._aircraft() or (0, 0, 0, 0))[3]
        metar = self._metar(icao)
        wind = metar_wind(metar)
        wet = is_wet(metar)
        approaches = await run.io_bound(self._generator.runway_approaches, icao)
        self._runways = await run.io_bound(self._divert.runways, icao)
        if not self._runways:
            self._airport_label.set_text(f"{icao}: no runways in the sim's apt.dat")
        else:
            self._airport_label.set_text(
                f"{row['city']} {row['iata']} ({icao}) {row['name']}: pick a runway"
            )
        rows = []
        for runway in self._runways:
            apps = approaches.get(runway.name, [])
            best = min((cls.tier for _, cls in apps), default=5)
            s = self._speeds(wind, runway)
            brake = autobrake(
                s.vapp, s.headwind, runway.elevation_ft, runway.length_ft, wet
            )
            rows.append(
                {
                    "rwy": runway.name,
                    "length": runway.length_ft,
                    "hdg": f"{runway.heading_mag(variation):03.0f}",
                    "wind": runway_wind(runway.name, wind),
                    "brake": f"{brake.mode or 'SHORT'} {brake.needed_ft:.0f}ft"
                    + (" wet" if wet else ""),
                    "brake_colour": BRAKE_COLOURS[brake.mode],
                    "brake_tip": f"VAPP {s.vapp:.0f} CONF {s.conf}, "
                    f"headwind {s.headwind:.0f}kt, with a margin and no reversers",
                    "ils": ils_text(runway),
                    "app": ", ".join(approach_text(n, c) for n, c in apps) or "Visual",
                    "app_colour": approach_colour(best),
                }
            )
        self._runways_table.rows = rows
        self._runways_table.selected = []
        self._runways_table.update()

    def _select_runway(self, e):
        if not e.selection or not self._airport:
            return
        name = e.selection[0]["rwy"]
        runway = next(r for r in self._runways if r.name == name)
        row = self._airport
        label = f"{row['city']} {row['iata']} ({row['icao']})"
        self._dialog.close()
        self._on_divert(row["icao"], label, runway)
