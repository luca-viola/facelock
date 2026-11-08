import Clutter from 'gi://Clutter';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {cameraToScreen, pupilOffset} from './gaze.js';

// Proportions after xeyes: two tall ovals with a black outline.
const EYE_HEIGHT = 0.55; // Share of the monitor's height.
const EYE_ASPECT = 0.7; // Width over height.
const GAP = 0.08; // Between the eyes, relative to an eye's width.
const OUTLINE = 0.09; // Relative to an eye's width.
const PUPIL = 0.3; // Pupil diameter, relative to an eye's width.
const PUPIL_TRAVEL = 0.9; // Keeps a pupil from touching the outline.
const BUTTON_GAP = 24;
// A little longer than a frame at 30 fps, so the pupils glide between snaps.
const LOOK_MS = 90;

const BUTTON_STYLE = 'font-size: 22px; font-weight: bold; padding: 12px 40px; border-radius: 999px;';

// A pair of giant eyes in the middle of the primary monitor, looking at a position in
// the camera image. Only the eyes and Dismiss take clicks, so the rest of the screen
// stays usable. Double-clicking an eye dismisses them, like the button.
export class Eyes {
    constructor(onDismiss) {
        this._onDismiss = onDismiss;
        this._gaze = {x: 0.5, y: 0.5};
        this._pupils = [];

        this._actor = new St.Widget({reactive: false});
        this._actor.connect('key-press-event', (_actor, event) => {
            if (event.get_key_symbol() === Clutter.KEY_Escape)
                this._onDismiss();
            return Clutter.EVENT_STOP;
        });
        Main.layoutManager.addTopChrome(this._actor);
        // If the overview or a dialog has already grabbed input, Dismiss would never
        // get the click, so take a grab over it. Esc works too in that case.
        this._grab = Main.modalCount > 0 ? Main.pushModal(this._actor) : null;
        Main.layoutManager.connectObject('monitors-changed', () => this._build(), this._actor);
        this._build();
    }

    destroy() {
        if (this._grab)
            Main.popModal(this._grab);
        this._actor.destroy();
        this._actor = null;
    }

    lookAt(x, y) {
        this._gaze = {x, y};
        this._aim(LOOK_MS);
    }

    _build() {
        this._actor.destroy_all_children();
        this._pupils = [];
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        this._monitor = monitor;
        this._actor.set_position(monitor.x, monitor.y);
        this._actor.set_size(monitor.width, monitor.height);

        const dismiss = new St.Button({
            label: 'Dismiss',
            style_class: 'button',
            style: BUTTON_STYLE,
            reactive: true,
            can_focus: false,
        });
        dismiss.connect('clicked', () => this._onDismiss());
        const [, buttonWidth] = dismiss.get_preferred_width(-1);
        const [, buttonHeight] = dismiss.get_preferred_height(-1);

        const height = monitor.height * EYE_HEIGHT;
        const width = height * EYE_ASPECT;
        const gap = width * GAP;
        const top = (monitor.height - height - BUTTON_GAP - buttonHeight) / 2;
        const left = (monitor.width - 2 * width - gap) / 2;
        this._addEye(left + width / 2, top + height / 2, width, height);
        this._addEye(left + width * 1.5 + gap, top + height / 2, width, height);

        this._actor.add_child(dismiss);
        dismiss.set_position(
            Math.round((monitor.width - buttonWidth) / 2),
            Math.round(top + height + BUTTON_GAP));
        this._aim(0);
    }

    _addEye(x, y, width, height) {
        const outline = width * OUTLINE;
        const ball = new St.DrawingArea({
            x: Math.round(x - width / 2),
            y: Math.round(y - height / 2),
            width: Math.round(width),
            height: Math.round(height),
            reactive: true,
        });
        ball.connect('button-press-event', (_actor, event) => {
            if (event.get_button() === Clutter.BUTTON_PRIMARY && this._isDoubleClick(event))
                this._onDismiss();
            return Clutter.EVENT_STOP;
        });
        ball.connect('repaint', area => {
            const [w, h] = area.get_surface_size();
            const cr = area.get_context();
            const ellipse = (inset, red, green, blue) => {
                cr.save();
                cr.translate(w / 2, h / 2);
                cr.scale(w / 2 - inset, h / 2 - inset);
                cr.arc(0, 0, 1, 0, 2 * Math.PI);
                cr.restore();
                cr.setSourceRGB(red, green, blue);
                cr.fill();
            };
            ellipse(0, 0, 0, 0);
            ellipse(outline, 1, 1, 1);
            cr.$dispose();
        });
        this._actor.add_child(ball);

        const radius = Math.round(width * PUPIL / 2);
        const pupil = new St.Widget({
            width: radius * 2,
            height: radius * 2,
            style: `background-color: black; border-radius: ${radius}px;`,
        });
        this._actor.add_child(pupil);
        this._pupils.push({
            actor: pupil,
            radius,
            eye: {x, y},
            rangeX: (width / 2 - outline - radius) * PUPIL_TRAVEL,
            rangeY: (height / 2 - outline - radius) * PUPIL_TRAVEL,
        });
    }

    // Clutter doesn't count clicks, so this compares with the previous press using
    // the desktop's double-click settings.
    _isDoubleClick(event) {
        const {double_click_time: time, double_click_distance: distance} = Clutter.Settings.get_default();
        const [x, y] = event.get_coords();
        const now = event.get_time();
        const last = this._lastPress;
        const double = last !== undefined && now - last.time <= time &&
            Math.hypot(x - last.x, y - last.y) <= distance;
        this._lastPress = double ? undefined : {time: now, x, y};
        return double;
    }

    _aim(duration) {
        if (!this._pupils.length)
            return;
        const {width, height} = this._monitor;
        const target = cameraToScreen(this._gaze.x, this._gaze.y, width, height);
        for (const {actor, radius, eye, rangeX, rangeY} of this._pupils) {
            const offset = pupilOffset(eye, target, rangeX, rangeY, width);
            actor.ease({
                x: Math.round(eye.x + offset.x - radius),
                y: Math.round(eye.y + offset.y - radius),
                duration,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        }
    }
}
