import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {Eyes} from './eyes.js';

// Carries out what a trigger from the daemon asks for.
export class Actions {
    // setTracking(true) asks the daemon to snap at full speed, for the eyes to follow.
    constructor(settings, setTracking) {
        this._settings = settings;
        this._setTracking = setTracking;
        this._returnWorkspace = null;
        this._eyes = null;
        this._intruderAt = {x: 0.5, y: 0.5};
        this._minimized = new Set();
    }

    // Leaves minimized windows minimized, which is the safe side after a lock.
    destroy() {
        this.closeEyes();
        this._forgetMinimized();
    }

    lock() {
        if (!Main.screenShield) {
            Main.notifyError('Face Guard', 'Can\'t lock the screen: this session has no lock screen.');
            return;
        }
        Main.screenShield.lock(true);
    }

    intruder(otherFaces) {
        this._minimizeApps();
        switch (this._settings.get_string('intruder-action')) {
        case 'lock':
            this.lock();
            break;
        case 'command':
            this._runCommand(otherFaces);
            break;
        case 'workspace':
            this._moveToWorkspace();
            break;
        case 'notify':
            Main.notify('Face Guard', 'Someone else is looking at your screen.');
            break;
        case 'eyes':
            this._showEyes();
            break;
        }
    }

    // Where the other face is in the camera image, from 0 to 1 on each axis.
    intruderAt(x, y) {
        this._intruderAt = {x, y};
        this._eyes?.lookAt(x, y);
    }

    closeEyes() {
        if (!this._eyes)
            return;
        this._eyes.destroy();
        this._eyes = null;
        this._setTracking(false);
    }

    // Dismissing only closes the eyes. They come back because the daemon triggers
    // once per episode, so the next trigger means the face left and returned.
    _showEyes() {
        if (this._eyes)
            return;
        this._eyes = new Eyes(() => this.closeEyes());
        this._eyes.lookAt(this._intruderAt.x, this._intruderAt.y);
        this._setTracking(true);
    }

    // Minimizes the chosen apps' windows on every workspace, remembering which ones
    // this did so they can be restored. A failure mustn't stop the main action.
    // The chosen apps' windows, or with All open apps every normal window. Windows left out of
    // the taskbar, such as the desktop icons, stay, like Finder on macOS.
    _windowsToMinimize() {
        if (this._settings.get_boolean('minimize-all')) {
            return global.display.list_all_windows().filter(window =>
                window.get_window_type() === Meta.WindowType.NORMAL && !window.is_skip_taskbar());
        }
        const appSystem = Shell.AppSystem.get_default();
        return this._settings.get_strv('minimize-apps')
            .flatMap(id => appSystem.lookup_app(id)?.get_windows() ?? []);
    }

    _minimizeApps() {
        for (const window of this._windowsToMinimize()) {
            if (window.minimized || !window.can_minimize())
                continue;
            try {
                window.minimize();
            } catch (error) {
                console.error(`Face Guard: can't minimize "${window.get_title()}": ${error.message}`);
                continue;
            }
            this._minimized.add(window);
            // Forgets windows that close, or that the user restores themselves.
            window.connectObject(
                'unmanaged', () => this._forget(window),
                'notify::minimized', () => {
                    if (!window.minimized)
                        this._forget(window);
                }, this);
        }
    }

    _forget(window) {
        window.disconnectObject(this);
        this._minimized.delete(window);
    }

    _forgetMinimized() {
        for (const window of [...this._minimized])
            this._forget(window);
    }

    _restoreApps() {
        const windows = [...this._minimized];
        this._forgetMinimized();
        if (!this._settings.get_boolean('minimize-restore'))
            return;
        for (const window of windows)
            window.unminimize();
    }

    clear() {
        this.closeEyes();
        this._restoreApps();
        if (this._returnWorkspace === null)
            return;
        const {target, previous} = this._returnWorkspace;
        this._returnWorkspace = null;
        if (!this._settings.get_boolean('return-on-clear'))
            return;
        // If the user has since moved elsewhere, leave them where they are.
        const manager = global.workspace_manager;
        if (manager.get_active_workspace_index() !== target)
            return;
        manager.get_workspace_by_index(previous)?.activate(global.get_current_time());
    }

    _moveToWorkspace() {
        const manager = global.workspace_manager;
        const wanted = this._settings.get_int('intruder-workspace') - 1;
        const target = Math.min(wanted, manager.get_n_workspaces() - 1);
        const previous = manager.get_active_workspace_index();
        if (target === previous)
            return;
        this._returnWorkspace = {target, previous};
        manager.get_workspace_by_index(target).activate(global.get_current_time());
    }

    _runCommand(otherFaces) {
        const command = this._settings.get_string('intruder-command').trim();
        if (!command) {
            Main.notifyError('Face Guard', 'Another face appeared, but no command is configured.');
            return;
        }
        try {
            const launcher = new Gio.SubprocessLauncher({flags: Gio.SubprocessFlags.NONE});
            launcher.setenv('FACEGUARD_OTHER_FACES', String(otherFaces), true);
            launcher.set_cwd(GLib.get_home_dir());
            const process = launcher.spawnv(['/bin/sh', '-c', command]);
            process.wait_check_async(null, (proc, result) => {
                try {
                    proc.wait_check_finish(result);
                } catch (error) {
                    Main.notifyError('Face Guard', `The command failed: ${error.message}`);
                }
            });
        } catch (error) {
            Main.notifyError('Face Guard', `Can't run the command: ${error.message}`);
        }
    }
}
