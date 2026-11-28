import logging

from nicegui import ui

logger = logging.getLogger(__name__)

SVG_DIAMOND = (
    lambda color: f'<svg version="1.0" xmlns="http://www.w3.org/2000/svg" width="80" height="80"><polygon points="0 40,40 80,80 40,40 0" style=" fill: {color}; stroke:black;"/></svg>'
)
ICON_DIAMOND = lambda color: (
    f"L.icon({{iconSize: [12, 12], iconUrl: 'data:image/svg+xml,{SVG_DIAMOND(color)}'}})"
)
SVG_PLANE = '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" width="123" height="123"><path d="M16.63,105.75c0.01-4.03,2.3-7.97,6.03-12.38L1.09,79.73c-1.36-0.59-1.33-1.42-0.54-2.4l4.57-3.9 c0.83-0.51,1.71-0.73,2.66-0.47l26.62,4.5l22.18-24.02L4.8,18.41c-1.31-0.77-1.42-1.64-0.07-2.65l7.47-5.96l67.5,18.97L99.64,7.45 c6.69-5.79,13.19-8.38,18.18-7.15c2.75,0.68,3.72,1.5,4.57,4.08c1.65,5.06-0.91,11.86-6.96,18.86L94.11,43.18l18.97,67.5 l-5.96,7.47c-1.01,1.34-1.88,1.23-2.65-0.07L69.43,66.31L45.41,88.48l4.5,26.62c0.26,0.94,0.05,1.82-0.47,2.66l-3.9,4.57 c-0.97,0.79-1.81,0.82-2.4-0.54l-13.64-21.57c-4.43,3.74-8.37,6.03-12.42,6.03C16.71,106.24,16.63,106.11,16.63,105.75 L16.63,105.75z" style=" fill: orange; stroke:black;"/></svg>'
ICON_PLANE = (
    f"L.icon({{iconSize: [24, 24], iconUrl: 'data:image/svg+xml,{SVG_PLANE}'}})" ""
)
# Plugin that lets markers take a rotationAngle, for the aircraft heading
ROTATED_MARKER_JS = (
    "https://unpkg.com/leaflet-rotatedmarker@0.2.0/leaflet.rotatedMarker.js"
)
# The plane icon points north-east
PLANE_ICON_ROTATION = -45
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
# Zoom for a route of a single point, which has no extent to fit
SINGLE_POINT_ZOOM = 8


def remove_layers(leaflet: ui.leaflet, layers):
    for layer in layers:
        try:
            leaflet.remove_layer(layer)
        except Exception:
            logger.debug("Could not remove existing layer")


def draw_route(leaflet: ui.leaflet, segments) -> list:
    """Draw (segment, waypoints) legs as coloured lines with a named diamond
    at each fix; returns the layers added"""
    layers = []
    # Consecutive segments share the fix they join at, which belongs in both
    # polylines but only needs one marker
    plotted = set()
    for segment, waypoints in segments:
        colour = SEGMENT_COLOURS[segment]
        icon = ICON_DIAMOND(colour)
        for waypoint in waypoints:
            # Points marked separately, such as the aircraft, set marker False
            if waypoint.name in plotted or not getattr(waypoint, "marker", True):
                continue
            plotted.add(waypoint.name)
            marker = leaflet.marker(latlng=(waypoint.latitude, waypoint.longitude))
            layers.append(marker)
            marker.run_method(":setIcon", icon)
            marker.run_method("bindTooltip", waypoint.name, TOOLTIP_OPTIONS)
        if len(waypoints) > 1:
            layers.append(
                leaflet.generic_layer(
                    name="polyline",
                    args=[
                        [(w.latitude, w.longitude) for w in waypoints],
                        {"color": colour, "weight": 2},
                    ],
                )
            )
    return layers


def fit_route(leaflet: ui.leaflet, segments, padding=20) -> bool:
    """Zoom the map to the route; False when it has no points"""
    points = [(w.latitude, w.longitude) for _, waypoints in segments for w in waypoints]
    if not points:
        return False
    lats, lons = zip(*points)
    if min(lats) == max(lats) and min(lons) == max(lons):
        leaflet.run_map_method("setView", points[0], SINGLE_POINT_ZOOM)
        return True
    leaflet.run_map_method(
        "fitBounds",
        [[min(lats), min(lons)], [max(lats), max(lons)]],
        {"padding": [padding, padding]},
    )
    return True


class RouteMap:
    """Small map showing one route, fitted to it, and optionally the aircraft.
    It redraws whenever the map initialises, as a map in a dialog does each
    time the dialog opens, since icons, tooltips and the view are not part of
    the layers' saved state."""

    def __init__(self):
        self.leaflet = ui.leaflet(zoom=5, additional_resources=[ROTATED_MARKER_JS])
        self._segments = []
        self._aircraft = None
        self._layers = []
        self.leaflet.on("init", self._draw)

    def show(self, segments, aircraft=None):
        """aircraft is (lat, lon, heading) or None"""
        self._segments = segments
        self._aircraft = aircraft
        self._draw()

    def _draw(self):
        remove_layers(self.leaflet, self._layers)
        self._layers = draw_route(self.leaflet, self._segments)
        if self._aircraft:
            lat, lon, heading = self._aircraft
            marker = self.leaflet.marker(
                latlng=(lat, lon),
                options={
                    "rotationOrigin": "center center",
                    "rotationAngle": (heading or 0) + PLANE_ICON_ROTATION,
                },
            )
            marker.run_method(":setIcon", ICON_PLANE)
            self._layers.append(marker)
        fit_route(self.leaflet, self._segments, padding=10)
