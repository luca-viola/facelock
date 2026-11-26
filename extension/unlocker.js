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

        this._label = new St.Label({
            style: 'font-size: 15pt; color: white; background-color: rgba(0,0,0,0.55); ' +
                'padding: 10px 18px; border-radius: 12px; text-align: center;',
            visible: false,
            // The lock screen's layer lays out with a BinLayout, which stretches a child over the
            // whole screen unless told otherwise. So: centred, at the bottom, clear of the edge.
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.END,
            x_expand: true,
            y_expand: true,
            margin_bottom: 96,
        });
        Main.layoutManager.screenShieldGroup.add_child(this._label);

        if (lockedByIntruder) {
            // Whoever made it lock may still be there, so it's for the password.
            this._say('Locked because someone else was in view. Use your password.');
            return;
        }
        this._armTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, ARM_DELAY_S, () => {
            this._armTimer = 0;
            this._arm();
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        if (this._armTimer)
            GLib.source_remove(this._armTimer);
        this._armTimer = 0;
        if (this._watchId)
            this._idleMonitor.remove_watch(this._watchId);
        this._watchId = 0;
        this._daemon?.stop();
        this._daemon = null;
        this._label.destroy();
    }

    _say(text) {
        this._label.text = text ?? '';
        this._label.visible = Boolean(text);
        // Kept above the lock screen's own widgets, which it adds after this.
        Main.layoutManager.screenShieldGroup.set_child_above_sibling(this._label, null);
    }

    // Waits for the next key press, click or mouse movement.
    _arm() {
        this._watchId = this._idleMonitor.add_user_active_watch(() => {
            this._watchId = 0;
            this._try();
        });
    }

    _try() {
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
