"""A pair of giant eyes in the middle of the main screen, looking at someone in the camera image.

Ported from the GNOME extension's eyes.js. The window is only as big as the eyes and the
Dismiss button, so the rest of the screen stays usable. Double-clicking an eye, the
button and Esc all dismiss them.
"""

import math

import objc
from AppKit import (NSBackingStoreBuffered, NSBezierPath, NSButton, NSColor, NSScreen, NSView,
                    NSWindow, NSMakeRect)
from Foundation import NSRunLoop, NSRunLoopCommonModes, NSTimer

from gaze import camera_to_screen, pupil_offset

# Proportions after xeyes: two tall ovals with a black outline.
EYE_HEIGHT = 0.55  # share of the screen's height
EYE_ASPECT = 0.7  # width over height
GAP = 0.08  # between the eyes, relative to an eye's width
OUTLINE = 0.09  # relative to an eye's width
PUPIL = 0.3  # pupil diameter, relative to an eye's width
PUPIL_TRAVEL = 0.9  # keeps a pupil from touching the outline
BUTTON_GAP = 24
BUTTON_SIZE = (150, 40)
FRAME_S = 1 / 60
EASE = 0.3  # share of the remaining distance a pupil moves each frame

BORDERLESS = 0
SCREEN_SAVER_LEVEL = 1000
CAN_JOIN_ALL_SPACES = 1 << 0
FULL_SCREEN_AUXILIARY = 1 << 8
ESCAPE_KEY = 53


class _Window(NSWindow):
    def canBecomeKeyWindow(self):
        return True

    def keyDown_(self, event):
        if event.keyCode() == ESCAPE_KEY:
            self.contentView().dismiss_(None)


class _EyesView(NSView):
    def initWithFrame_eyes_pupils_onDismiss_(self, frame, eyes, pupils, on_dismiss):
        self = objc.super(_EyesView, self).initWithFrame_(frame)
        self._eyes = eyes  # (center x, center y, width, height) in view coordinates, y down
        self._pupils = pupils  # [x, y, radius, target x, target y] per eye
        self._on_dismiss = on_dismiss
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def acceptsFirstResponder(self):
        return True

    def dismiss_(self, _sender):
        self._on_dismiss()

    def mouseDown_(self, event):
        if event.clickCount() != 2:
            return
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        for cx, cy, width, height in self._eyes:
            if ((point.x - cx) / (width / 2)) ** 2 + ((point.y - cy) / (height / 2)) ** 2 <= 1:
                self._on_dismiss()
                return

    def drawRect_(self, _rect):
        for (cx, cy, width, height), (px, py, radius, _tx, _ty) in zip(self._eyes, self._pupils):
            outline = width * OUTLINE
            NSColor.blackColor().set()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - width / 2, cy - height / 2, width, height)).fill()
            NSColor.whiteColor().set()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(
                cx - width / 2 + outline, cy - height / 2 + outline,
                width - 2 * outline, height - 2 * outline)).fill()
            NSColor.blackColor().set()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(px - radius, py - radius, 2 * radius, 2 * radius)).fill()

    def step(self):
        """Moves each pupil toward its target. Returns whether anything moved."""
        moved = False
        for pupil in self._pupils:
            dx, dy = pupil[3] - pupil[0], pupil[4] - pupil[1]
            if abs(dx) < 0.5 and abs(dy) < 0.5:
                continue
            pupil[0] += dx * EASE
            pupil[1] += dy * EASE
            moved = True
        if moved:
            self.setNeedsDisplay_(True)
        return moved

    def jump(self):
        for pupil in self._pupils:
            pupil[0], pupil[1] = pupil[3], pupil[4]
        self.setNeedsDisplay_(True)


class _Ticker(objc.lookUpClass("NSObject")):
    def initWithView_(self, view):
        self = objc.super(_Ticker, self).init()
        self._view = view
        return self

    def tick_(self, _timer):
        self._view.step()


class Eyes:
    def __init__(self, on_dismiss):
        self._gaze = (0.5, 0.5)
        screen = NSScreen.screens()[0]  # the one with the menu bar
        screen_frame = screen.frame()
        screen_width, screen_height = screen_frame.size.width, screen_frame.size.height

        height = screen_height * EYE_HEIGHT
        width = height * EYE_ASPECT
        gap = width * GAP
        total_width = 2 * width + gap
        total_height = height + BUTTON_GAP + BUTTON_SIZE[1]
        # In screen coordinates, y down, to share the maths with the GNOME version.
        left = (screen_width - total_width) / 2
        top = (screen_height - total_height) / 2
        self._screen_size = (screen_width, screen_height)
        self._origin = (left, top)

        eye_centers = [(width / 2, height / 2), (width * 1.5 + gap, height / 2)]
        self._eyes = [(cx, cy, width, height) for cx, cy in eye_centers]
        radius = width * PUPIL / 2
        self._ranges = [((width / 2 - width * OUTLINE - radius) * PUPIL_TRAVEL,
                         (height / 2 - width * OUTLINE - radius) * PUPIL_TRAVEL) for _ in eye_centers]
        pupils = [[cx, cy, radius, cx, cy] for cx, cy in eye_centers]

        frame = NSMakeRect(screen_frame.origin.x + left,
                           screen_frame.origin.y + screen_height - top - total_height,
                           total_width, total_height)
        self._window = _Window.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, BORDERLESS, NSBackingStoreBuffered, False)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setHasShadow_(False)
        self._window.setLevel_(SCREEN_SAVER_LEVEL)
        self._window.setCollectionBehavior_(CAN_JOIN_ALL_SPACES | FULL_SCREEN_AUXILIARY)
        self._window.setReleasedWhenClosed_(False)

        self._view = _EyesView.alloc().initWithFrame_eyes_pupils_onDismiss_(
            NSMakeRect(0, 0, total_width, total_height), self._eyes, pupils, on_dismiss)
        button = NSButton.alloc().initWithFrame_(NSMakeRect(
            (total_width - BUTTON_SIZE[0]) / 2, height + BUTTON_GAP, *BUTTON_SIZE))
        button.setTitle_("Dismiss")
        button.setBezelStyle_(1)  # rounded
        button.setTarget_(self._view)
        button.setAction_("dismiss:")
        self._view.addSubview_(button)
        self._window.setContentView_(self._view)

        self._aim(instant=True)
        self._window.orderFrontRegardless()
        self._window.makeKeyWindow()
        self._ticker = _Ticker.alloc().initWithView_(self._view)
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            FRAME_S, self._ticker, "tick:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(self._timer, NSRunLoopCommonModes)

    def look_at(self, x, y):
        self._gaze = (x, y)
        self._aim()

    def _aim(self, instant=False):
        width, height = self._screen_size
        target = camera_to_screen(*self._gaze, width, height)
        left, top = self._origin
        for pupil, (cx, cy, _w, _h), (range_x, range_y) in zip(self._view._pupils, self._eyes, self._ranges):
            dx, dy = pupil_offset((left + cx, top + cy), target, range_x, range_y, width)
            pupil[3], pupil[4] = cx + dx, cy + dy
        if instant:
            self._view.jump()

    def destroy(self):
        self._timer.invalidate()
        self._window.orderOut_(None)
        self._window.close()
