import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// Carries out what a trigger from the daemon asks for.
export class Actions {
    constructor(settings) {
        this._settings = settings;
        this._returnWorkspace = null;
    }

    lock() {
        if (!Main.screenShield) {
            Main.notifyError('Face Guard', 'Can\'t lock the screen: this session has no lock screen.');
            return;
        }
        Main.screenShield.lock(true);
    }

    intruder(otherFaces) {
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
        }
    }

    clear() {
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
