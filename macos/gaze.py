"""Where the eyes' pupils point. Pure math, ported from the GNOME extension's gaze.js."""

import math

# How far in front of the screen the other person is assumed to be, in screen widths.
DEPTH_WIDTHS = 0.5
# Stretches positions past the screen edges, so that a face at the side of the camera
# image turns every eye that way, even the eyes already on that side of the screen.
SPREAD = 2


def camera_to_screen(x, y, width, height):
    """Converts a position in the camera image (0 to 1) to screen coordinates, y down.

    The camera faces the user, so someone on the left of its image is on the right of
    the screen. It's assumed to be at the top of the screen.
    """
    return width / 2 + (0.5 - x) * SPREAD * width, (y - 0.5) * SPREAD * height


def pupil_offset(eye, target, range_x, range_y, width):
    """How far a pupil moves from the center of its eye to look at a point in front of the screen."""
    dx = target[0] - eye[0]
    dy = target[1] - eye[1]
    distance = math.hypot(dx, dy, width * DEPTH_WIDTHS)
    return dx / distance * range_x, dy / distance * range_y
