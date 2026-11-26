import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {DaemonClient} from './daemonClient.js';

const MAX_ATTEMPTS = 3; // then only the password, until the next lock
// Activity this soon after locking is the hand that locked, such as releasing Super+L.
const ARM_DELAY_S = 5;

const STEPS = {
    look: 'Look at the camera',
    alone: 'Only you should be in view',
    turn: 'Turn your head to one side, then back',
};

// While the screen is locked: when someone wakes it, checks their face once, and with the phone
// option asks the paired phone too. Unlocks if both agree. The password always works as well.
export class Unlocker {
    // argv is the daemon command for one unlock check.
    constructor(argv, {lockedByIntruder}) {
        this._argv = argv;
        this._attempts = 0;
        this._daemon = null;
        this._result = null;
        this._watchId = 0;
        this._armTimer = 0;
        this._idleMonitor = global.backend.get_core_idle_monitor();

        // A message at the bottom of every screen, since you may be looking at any of them. It's
        // only on the lock screen while there's something to say: with it there all the time,
        // the lock screen sometimes froze.
        this._text = null;
        this._layer = null;
        Main.layoutManager.connectObject('monitors-changed', () => this._say(this._text), this);

        if (lockedByIntruder) {
            // Whoever made it lock may still be there, so it's for the password.
            this._say('Locked because someone else was in view. Use your password.');
            return;
        }
        console.log('Facelock: unlocker created');
        this._armTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, ARM_DELAY_S, () => {
            this._armTimer = 0;
            console.log('Facelock: unlocker armed');
            this._arm();
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        console.log('Facelock: unlocker destroyed');
        if (this._armTimer)
            GLib.source_remove(this._armTimer);
        this._armTimer = 0;
        if (this._watchId)
            this._idleMonitor.remove_watch(this._watchId);
        this._watchId = 0;
        this._daemon?.stop();
        this._daemon = null;
        Main.layoutManager.disconnectObject(this);
        this._removeLayer();
    }

    _removeLayer() {
        this._layer?.destroy();
        this._layer = null;
    }

    // The lock screen's layer stretches its children over the whole desktop, so this layer does,
    // and places a box over each monitor inside it.
    _addLayer() {
        this._layer = new St.Widget({layout_manager: new Clutter.FixedLayout(), x_expand: true, y_expand: true});
        for (const monitor of Main.layoutManager.monitors) {
            const box = new St.Widget({
                layout_manager: new Clutter.BinLayout(),
                x: monitor.x, y: monitor.y, width: monitor.width, height: monitor.height,
            });
            const label = new St.Label({
                style: 'font-size: 15pt; color: white; background-color: rgba(0,0,0,0.55); ' +
                    'padding: 10px 18px; border-radius: 12px; text-align: center;',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.END,
                x_expand: true,
                y_expand: true,
                margin_bottom: 96,
            });
            box.add_child(label);
            this._layer.add_child(box);
        }
        Main.layoutManager.screenShieldGroup.add_child(this._layer);
    }

    // Shows text on every screen, or removes the message with null. Rebuilt each time, which is
    // cheap, and also follows screens being plugged in or out.
    _say(text) {
        this._text = text ?? null;
        this._removeLayer();
        if (!this._text)
            return;
        this._addLayer();
        for (const box of this._layer.get_children())
            box.get_first_child().text = this._text;
    }

    // Waits for the next key press, click or mouse movement.
    _arm() {
        this._watchId = this._idleMonitor.add_user_active_watch(() => {
            this._watchId = 0;
            this._try();
        });
    }

    _try() {
        console.log(`Facelock: activity on the lock screen, attempt ${this._attempts + 1}`);
        if (this._daemon || this._attempts >= MAX_ATTEMPTS)
            return;
        this._attempts++;
        this._result = null;
        this._say('Starting the camera…');
        try {
            this._daemon = new DaemonClient(this._argv,
                message => this._onEvent(message),
                () => this._onExit());
        } catch (error) {
            this._daemon = null;
            this._fail(`Can't start Facelock: ${error.message}`);
        }
    }

    _onEvent(message) {
        switch (message.event) {
        case 'unlock_step':
            if (message.step === 'phone') {
                this._say(message.number === null || message.number === undefined
                    ? 'Approve on your phone'
                    : `Approve on your phone, and pick ${message.number}`);
            } else {
                this._say(STEPS[message.step] ?? null);
            }
            break;
        case 'unlock':
            this._result = message;
            break;
        case 'error':
            this._result = {ok: false, reason: message.message};
            break;
        }
    }

    _onExit() {
        this._daemon = null;
        const result = this._result ?? {ok: false, reason: 'Facelock stopped unexpectedly'};
        if (result.ok) {
            this._say(null);
            Main.screenShield.deactivate(true);
        } else {
            this._fail(result.reason);
        }
    }

    _fail(reason) {
        reason = String(reason).replace(/\.$/, '');
        if (this._attempts >= MAX_ATTEMPTS) {
            this._say(`${reason}. Use your password.`);
            return;
        }
        this._say(`${reason}. Move the mouse or press a key to try again.`);
        this._arm();
    }
}
