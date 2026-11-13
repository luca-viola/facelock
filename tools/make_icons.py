#!/usr/bin/env python3
"""Writes the panel's status icons to extension/icons, matching the macOS app's.

Needs Shapely 2 (pip install shapely); the extension itself doesn't. Run from anywhere:

    python tools/make_icons.py

GNOME recolors a symbolic icon by forcing the fill of its shapes to the panel's text color,
so every line here is built as a filled outline rather than a stroke. Coordinates are on an
18 by 18 grid, the macOS menu bar's size, with y pointing down as in SVG.
"""

import os

from shapely.geometry import LineString, LinearRing, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

SIZE = 18
LINE = 1.5  # outline width of the drawn icons
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extension", "icons")


def cubic(p0, p1, p2, p3, steps=24):
    """Points along a cubic Bézier curve, without its first point."""
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        points.append((
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        ))
    return points


def shield(inset_x, inset_y):
    """The macOS app's shield (StatusIcons.swift) in the 18-point square inset by these margins.

    The Swift code works with y pointing up, so y is flipped here.
    """
    left, bottom = inset_x, inset_y
    width, height = SIZE - 2 * inset_x, SIZE - 2 * inset_y

    def point(x, y):
        return (left + (x - 272) / 480 * width, SIZE - (bottom + (y - 220) / 590 * height))

    start = point(512, 810)
    points = [start]
    points += cubic(start, point(590, 755), point(680, 735), point(752, 735))
    points.append(point(752, 555))
    points += cubic(point(752, 555), point(752, 385), point(640, 285), point(512, 220))
    points += cubic(point(512, 220), point(384, 285), point(272, 385), point(272, 555))
    points.append(point(272, 735))
    points += cubic(point(272, 735), point(344, 735), point(434, 755), start)
    return points


def outline(shape, width=LINE):
    """The edge of a shape as a band of the given width, like a stroke with round joins."""
    return shape.exterior.buffer(width / 2, join_style="round")


def line(*points, width=LINE):
    return LineString(points).buffer(width / 2, cap_style="round", join_style="round")


# --- The shields: exactly the macOS shapes ---

def owner():
    """Filled shield with a thin shield cut into it: you're here."""
    filled = Polygon(shield(1.8, 0.5))
    cut = LinearRing(shield(4.6, 3.3)).buffer(1.1 / 2, join_style="round")
    return filled.difference(cut)


def absent():
    """Shield outline: you're not recognized."""
    return LinearRing(shield(2.6, 1.25)).buffer(1.5 / 2, join_style="round")


# --- The others: drawn for Face Guard in the same outline style ---

def person(head_x, head_y, head_radius, body_x, body_bottom, body_radius):
    """A head and rounded shoulders, as solid shapes."""
    head = Point(head_x, head_y).buffer(head_radius)
    shoulders = Point(body_x, body_bottom).buffer(body_radius).intersection(
        box(0, body_bottom - body_radius, SIZE, body_bottom))
    return head, shoulders


def intruder():
    """Two people: someone else is looking."""
    front = person(6.6, 7.0, 2.6, 6.6, 16.2, 4.9)
    back = person(12.6, 4.2, 2.3, 12.9, 13.4, 4.2)
    front_lines = unary_union([outline(part) for part in front])
    back_lines = unary_union([outline(part) for part in back])
    # The person behind stops short of the one in front, with a gap.
    front_space = unary_union(front).buffer(LINE / 2 + 0.9)
    return front_lines.union(back_lines.difference(front_space))


def eye_shape():
    """An almond: where two circles overlap."""
    half_width, half_height = 7.4, 4.5
    radius = (half_width**2 + half_height**2) / (2 * half_height)
    upper = Point(9, 9 - half_height + radius).buffer(radius, quad_segs=64)
    lower = Point(9, 9 + half_height - radius).buffer(radius, quad_segs=64)
    return upper.intersection(lower)


def starting():
    """An eye: starting to watch."""
    return outline(eye_shape()).union(Point(9, 9).buffer(2.6))


def off():
    """A crossed-out eye: not watching."""
    slash = ((3.0, 2.2), (15.0, 15.8))
    gap = LineString(slash).buffer(LINE / 2 + 1.1, cap_style="flat")
    return starting().difference(gap).union(line(*slash))


def error():
    """A warning triangle: Face Guard isn't watching."""
    corner = 1.3
    triangle = Polygon([(9, 1.6), (16.9, 15.6), (1.1, 15.6)]).buffer(-corner).buffer(corner)
    mark = line((9, 6.6), (9, 10.6), width=1.7)
    dot = Point(9, 13.0).buffer(1.0)
    return outline(triangle).union(mark).union(dot)


ICONS = {
    "owner": owner,
    "absent": absent,
    "intruder": intruder,
    "starting": starting,
    "off": off,
    "error": error,
}


def path_data(geometry: BaseGeometry):
    """SVG path data for a (multi)polygon; holes are subpaths filled with the even-odd rule."""
    geometry = geometry.simplify(0.01)
    polygons = getattr(geometry, "geoms", [geometry])
    rings = [ring for polygon in polygons for ring in (polygon.exterior, *polygon.interiors)]
    return " ".join(
        "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in ring.coords[:-1]) + " Z" for ring in rings)


def write(name, geometry):
    minx, miny, maxx, maxy = geometry.bounds
    assert minx >= 0 and miny >= 0 and maxx <= SIZE and maxy <= SIZE, f"{name} doesn't fit: {geometry.bounds}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 {SIZE} {SIZE}">\n'
        f'  <path fill="#2e3436" fill-rule="evenodd" d="{path_data(geometry)}"/>\n'
        "</svg>\n"
    )
    path = os.path.join(OUT_DIR, f"faceguard-{name}-symbolic.svg")
    with open(path, "w") as handle:
        handle.write(svg)
    return path


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, draw in ICONS.items():
        print(write(name, draw()))


if __name__ == "__main__":
    main()
