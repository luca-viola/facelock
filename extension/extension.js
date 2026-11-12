import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {Actions} from './actions.js';
import {DaemonClient} from './daemonClient.js';

const EXIT_FATAL = 4; // The daemon's "restarting won't help" exit code.
const RESTART_DEBOUNCE_MS = 800; // Sliders change settings many times per second.
const BACKOFF_MIN_S = 2;
const BACKOFF_MAX_S = 60;
const ENROLL_TIMEOUT_S = 180; // Monitoring must come back even if preferences crashes.

const RESTART_KEYS = [
    'camera-device', 'interval-ms', 'model', 'use-gpu', 'match-thresholds', 'detection-threshold',
    'min-face-px', 'absence-grace-s', 'intruder-grace-s', 'python-path', 'reference-stamp',
];

const ICONS = {
    off: 'camera-disabled-symbolic',
    starting: 'camera-web-symbolic',
    owner: 'security-high-symbolic',
    absent: 'security-low-symbolic',
    intruder: 'security-medium-symbolic',
    error: 'dialog-warning-symbolic',
};

const Indicator = GObject.registerClass(
class FaceGuardIndicator extends PanelMenu.Button {
    _init(extension, settings) {
        super._init(0.5, extension.metadata.name);

        this._icon = new St.Icon({icon_name: ICONS.off, style_class: 'system-status-icon'});
        this.add_child(this._icon);

        this._status = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.menu.addMenuItem(this._status);

        this._toggle = new PopupMenu.PopupSwitchMenuItem('Watch camera', settings.get_boolean('enabled'));
        this._toggle.connect('toggled', (_item, state) => settings.set_boolean('enabled', state));
        this.menu.addMenuItem(this._toggle);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addAction('Settings', () => extension.openPreferences());
    }

    setStatus(iconKey, text) {
        this._icon.icon_name = ICONS[iconKey];
        this._status.label.text = text;
    }

    setToggle(state) {
        this._toggle.setToggleState(state);
    }
});

export default class FaceGuardExtension extends Extension {
    // Disabled when the screen locks and enabled again on unlock, because the
    // metadata declares no session-modes. So the camera is off while locked, and
    // locking the screen can't fire again until the user has logged back in.
    enable() {
        this._settings = this.getSettings();
        this._settings.set_boolean('enroll-active', false);
        this._actions = new Actions(this._settings, on => this._daemon?.send(on ? 'track' : 'untrack'));
        this._indicator = new Indicator(this, this._settings);
        Main.panel.addToStatusArea(this.uuid, this._indicator);

        this._daemon = null;
        this._restartTimer = 0;
        this._debounceTimer = 0;
        this._enrollTimer = 0;
        this._backoffS = BACKOFF_MIN_S;
        this._lastError = null;

        this._settingsIds = [
            this._settings.connect('changed::enabled', () => {
                this._indicator.setToggle(this._settings.get_boolean('enabled'));
                this._backoffS = BACKOFF_MIN_S;
                this._sync();
            }),
            this._settings.connect('changed::enroll-active', () => this._onEnrollChanged()),
            ...RESTART_KEYS.map(key => this._settings.connect(`changed::${key}`, () => this._scheduleRestart())),
        ];
        this._sync();
    }

    disable() {
        this._settingsIds.forEach(id => this._settings.disconnect(id));
        this._settingsIds = null;
        this._clearTimer('_restartTimer');
        this._clearTimer('_debounceTimer');
        this._clearTimer('_enrollTimer');
        this._stopDaemon();
        this._indicator.destroy();
        this._indicator = null;
        this._actions.destroy();
        this._actions = null;
        this._settings = null;
    }

    _clearTimer(name) {
        if (this[name]) {
            GLib.source_remove(this[name]);
            this[name] = 0;
        }
    }

    _referencePath() {
        return GLib.build_filenamev([GLib.get_user_data_dir(), 'faceguard', 'reference.jpg']);
    }

    _daemonArgv() {
        const s = this._settings;
        const model = s.get_string('model');
        const threshold = s.get_value('match-thresholds').deepUnpack()[model];
        return [
            s.get_string('python-path') || 'python3',
            GLib.build_filenamev([this.path, 'daemon', 'faceguard_daemon.py']),
            '--reference', this._referencePath(),
            '--device', s.get_string('camera-device'),
            '--interval-ms', String(s.get_int('interval-ms')),
            '--detection-threshold', String(s.get_double('detection-threshold')),
            '--min-face-px', String(s.get_int('min-face-px')),
            '--absence-grace', String(s.get_double('absence-grace-s')),
            '--intruder-grace', String(s.get_double('intruder-grace-s')),
            '--model', model,
            '--compute', s.get_boolean('use-gpu') ? 'gpu' : 'cpu',
            // Without one set for this model, the daemon uses the model's own default.
            ...threshold === undefined ? [] : ['--match-threshold', String(threshold)],
        ];
    }

    // Starts or stops the daemon to match the settings, and shows why if it's off.
    _sync() {
        this._clearTimer('_restartTimer');
        this._stopDaemon();

        if (!this._settings.get_boolean('enabled')) {
            this._indicator.setStatus('off', 'Not watching');
            return;
        }
        if (this._settings.get_boolean('enroll-active')) {
            this._indicator.setStatus('off', 'Paused while taking a reference photo');
            return;
        }
        if (!GLib.file_test(this._referencePath(), GLib.FileTest.EXISTS)) {
            this._showError('Set a reference image in Settings first');
            return;
        }
        this._indicator.setStatus('starting', 'Starting…');
        try {
            this._daemon = new DaemonClient(
                this._daemonArgv(),
                message => this._onDaemonEvent(message),
                status => this._onDaemonExit(status));
        } catch (error) {
            this._showError(`Can't start the daemon: ${error.message}`);
        }
    }

    // Also closes the eyes, because a stopped daemon can't say the face has gone.
    _stopDaemon() {
        this._actions.closeEyes();
        this._daemon?.stop();
        this._daemon = null;
    }

    _scheduleRestart() {
        this._clearTimer('_debounceTimer');
        this._debounceTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, RESTART_DEBOUNCE_MS, () => {
            this._debounceTimer = 0;
            this._backoffS = BACKOFF_MIN_S;
            this._sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    _onEnrollChanged() {
        this._clearTimer('_enrollTimer');
        if (this._settings.get_boolean('enroll-active')) {
            this._enrollTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, ENROLL_TIMEOUT_S, () => {
                this._enrollTimer = 0;
                this._settings.set_boolean('enroll-active', false);
                return GLib.SOURCE_REMOVE;
            });
        }
        this._sync();
    }

    _onDaemonEvent(message) {
        switch (message.event) {
        case 'loading':
            this._indicator.setStatus('starting', message.detail);
            break;
        case 'ready':
            this._lastError = null;
            this._backoffS = BACKOFF_MIN_S;
            this._running = `${message.model} on the ${message.compute.toUpperCase()}`;
            this._indicator.setStatus('starting', `Watching with ${this._running}`);
            if (message.requested === 'gpu' && message.compute === 'cpu')
                this._warnGpuUnavailable();
            break;
        case 'status':
            this._showStatus(message);
            break;
        case 'intruder_at':
            this._actions.intruderAt(message.x, message.y);
            break;
        case 'trigger':
            this._onTrigger(message);
            break;
        case 'error':
            this._showError(message.message);
            break;
        }
    }

    _showStatus({state, others, score, camera_fps: fps, snap_rate: rate}) {
        const match = score === null ? 'no face seen' : `match ${score.toFixed(2)}`;
        const speed = `${rate.toFixed(1)} snaps/s, camera ${fps.toFixed(0)} fps · ${this._running}`;
        const summary = {
            owner: 'You\'re here',
            absent: 'You\'re not recognized',
            intruder: `You and ${others} other${others > 1 ? 's' : ''}`,
        }[state];
        this._indicator.setStatus(state, `${summary} · ${match}\n${speed}`);
    }

    // Once per login, because the daemon restarts after every unlock.
    _warnGpuUnavailable() {
        if (this._gpuWarned)
            return;
        this._gpuWarned = true;
        Main.notify('Face Guard is running on the CPU',
            'Use GPU is on, but the GPU couldn\'t be used. Check your NVIDIA driver and CUDA setup.');
    }

    _onTrigger({kind, others}) {
        try {
            if (kind === 'absent')
                this._actions.lock();
            else if (kind === 'intruder')
                this._actions.intruder(others);
            else if (kind === 'clear')
                this._actions.clear();
        } catch (error) {
            console.error(`Face Guard: ${kind} action failed: ${error.message}`);
            Main.notifyError('Face Guard', `The ${kind} action failed: ${error.message}`);
        }
    }

    _onDaemonExit(status) {
        this._daemon = null;
        this._actions.closeEyes();
        if (status === EXIT_FATAL)
            return;
        // While this is retrying nothing is being watched, so _showError has
        // already told the user. Keep trying in case the camera comes back.
        this._indicator.setStatus('error', `${this._lastError ?? 'The daemon stopped'}. Retrying…`);
        this._restartTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, this._backoffS, () => {
            this._restartTimer = 0;
            this._sync();
            return GLib.SOURCE_REMOVE;
        });
        this._backoffS = Math.min(this._backoffS * 2, BACKOFF_MAX_S);
    }

    // Notifies once per distinct problem, because the guard isn't protecting
    // anything until it's fixed and a panel icon is easy to miss.
    _showError(text) {
        this._indicator.setStatus('error', text);
        if (text !== this._lastError)
            Main.notifyError('Face Guard isn\'t watching', text);
        this._lastError = text;
    }
}
