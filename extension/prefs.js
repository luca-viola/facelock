import Adw from 'gi://Adw';
import Gdk from 'gi://Gdk';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

const ACTIONS = [
    ['lock', 'Lock the screen'],
    ['workspace', 'Switch workspace'],
    ['command', 'Run a command'],
    ['notify', 'Show a notification'],
    ['eyes', 'Show giant eyes'],
];

// Reads a daemon's JSON-line events, calling onEvent for each one.
function runDaemon(argv, onEvent, onExit) {
    const process = Gio.Subprocess.new(
        argv, Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE);
    const stdout = new Gio.DataInputStream({base_stream: process.get_stdout_pipe()});
    const readLine = () => {
        stdout.read_line_async(GLib.PRIORITY_DEFAULT, null, (stream, result) => {
            let line = null;
            try {
                [line] = stream.read_line_finish_utf8(result);
            } catch {
                // The pipe closed with the process; wait_async reports the exit.
            }
            if (line === null)
                return;
            try {
                onEvent(JSON.parse(line));
            } catch (error) {
                console.warn(`Face Guard: bad daemon output: ${error.message}`);
            }
            readLine();
        });
    };
    readLine();
    process.wait_async(null, () => onExit?.());
    return process;
}

export default class FaceGuardPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        this._settings = this.getSettings();
        window.set_default_size(640, 820);
        window._settings = this._settings;

        const page = new Adw.PreferencesPage();
        window.add(page);
        page.add(this._buildReferenceGroup(window));
        page.add(this._buildCameraGroup());
        page.add(this._buildDetectionGroup());
        page.add(this._buildActionGroup());
        page.add(this._buildMinimizeGroup(window));
        page.add(this._buildAdvancedGroup());
    }

    _daemonBase() {
        return [
            this._settings.get_string('python-path') || 'python3',
            GLib.build_filenamev([this.path, 'daemon', 'faceguard_daemon.py']),
        ];
    }

    _referencePath() {
        return GLib.build_filenamev([GLib.get_user_data_dir(), 'faceguard', 'reference.jpg']);
    }

    /// --- REFERENCE FACE --- ///
    _buildReferenceGroup(window) {
        const group = new Adw.PreferencesGroup({
            title: 'Your face',
            description: 'The image every camera snap is compared to. It must show only your face.',
        });

        this._referencePicture = new Gtk.Picture({
            content_fit: Gtk.ContentFit.CONTAIN,
            height_request: 200,
            margin_bottom: 12,
        });
        group.add(this._referencePicture);

        this._referenceRow = new Adw.ActionRow();
        const takePhoto = new Gtk.Button({label: 'Take Photo', valign: Gtk.Align.CENTER});
        takePhoto.connect('clicked', () => this._openCaptureDialog(window));
        const chooseFile = new Gtk.Button({label: 'Choose File', valign: Gtk.Align.CENTER});
        chooseFile.connect('clicked', () => this._chooseFile(window));
        this._spinner = new Adw.Spinner({visible: false});
        this._referenceRow.add_suffix(this._spinner);
        this._referenceRow.add_suffix(takePhoto);
        this._referenceRow.add_suffix(chooseFile);
        group.add(this._referenceRow);

        const enabled = new Adw.SwitchRow({title: 'Watch camera'});
        this._settings.bind('enabled', enabled, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(enabled);

        this._refreshReference();
        return group;
    }

    _refreshReference(message = null) {
        const path = this._referencePath();
        const exists = GLib.file_test(path, GLib.FileTest.EXISTS);
        let status = exists ? 'Reference image is set' : 'No reference image yet';
        let texture = null;
        if (exists) {
            // A damaged file must not stop the window opening, since this is where
            // a new reference gets set.
            try {
                texture = Gdk.Texture.new_from_filename(path);
            } catch {
                status = 'The reference image can\'t be read. Set a new one.';
            }
        }
        this._referencePicture.visible = texture !== null;
        this._referencePicture.set_paintable(texture);
        this._referenceRow.title = message ?? status;
    }

    _chooseFile(window) {
        const filter = new Gtk.FileFilter({name: 'Images'});
        filter.add_pixbuf_formats();
        const filters = new Gio.ListStore({item_type: Gtk.FileFilter});
        filters.append(filter);
        const dialog = new Gtk.FileDialog({title: 'Choose an image of your face', filters});
        dialog.open(window, null, (source, result) => {
            let file;
            try {
                file = source.open_finish(result);
            } catch {
                return; // Dismissed.
            }
            this._enroll(file.get_path());
        });
    }

    // Validates and stores an image as the reference, then tells the extension.
    _enroll(sourcePath, onDone = null) {
        this._spinner.visible = true;
        this._refreshReference('Checking the image…');
        let outcome = null;
        try {
            runDaemon(
                [...this._daemonBase(), '--enroll', sourcePath, '--reference', this._referencePath(),
                    '--detection-threshold', String(this._settings.get_double('detection-threshold'))],
                message => {
                    if (message.event === 'loading')
                        this._refreshReference(message.detail);
                    else
                        outcome = message;
                },
                () => {
                    this._spinner.visible = false;
                    if (outcome?.event === 'enrolled') {
                        this._settings.set_int64('reference-stamp', GLib.get_real_time());
                        this._refreshReference();
                    } else {
                        this._refreshReference(outcome?.message ?? 'The check failed; see the system journal');
                    }
                    onDone?.();
                });
        } catch (error) {
            this._spinner.visible = false;
            this._refreshReference(`Can't start the daemon: ${error.message}`);
            onDone?.();
        }
    }

    _openCaptureDialog(window) {
        const picture = new Gtk.Picture({
            content_fit: Gtk.ContentFit.CONTAIN,
            width_request: 560,
            height_request: 315,
            margin_start: 12,
            margin_end: 12,
        });
        const statusLabel = new Gtk.Label({label: 'Starting the camera…', margin_top: 12});
        const snapButton = new Gtk.Button({
            label: 'Snap',
            sensitive: false,
            halign: Gtk.Align.CENTER,
            margin_top: 12,
            margin_bottom: 12,
            css_classes: ['suggested-action', 'pill'],
        });
        const box = new Gtk.Box({orientation: Gtk.Orientation.VERTICAL});
        box.append(picture);
        box.append(statusLabel);
        box.append(snapButton);
        const toolbar = new Adw.ToolbarView({content: box});
        toolbar.add_top_bar(new Adw.HeaderBar());
        const dialog = new Adw.Dialog({title: 'Take a Reference Photo', child: toolbar});

        // The extension has to let go of the camera first; the daemon retries
        // opening it until that has happened.
        this._settings.set_boolean('enroll-active', true);
        let process = null;
        let capturedPath = null;
        let failure = null;
        let closed = false;

        const finish = () => {
            if (!capturedPath) {
                this._settings.set_boolean('enroll-active', false);
                return;
            }
            this._enroll(capturedPath, () => {
                GLib.unlink(capturedPath);
                this._settings.set_boolean('enroll-active', false);
            });
        };

        snapButton.connect('clicked', () => {
            snapButton.sensitive = false;
            process.get_stdin_pipe().write_bytes(new GLib.Bytes('snap\n'), null);
        });

        dialog.connect('closed', () => {
            closed = true;
            // Closing stdin lets the daemon delete its preview image and exit,
            // and its exit handler then calls finish().
            if (process)
                process.get_stdin_pipe().close(null);
            else
                finish();
        });

        try {
            process = runDaemon(
                [...this._daemonBase(), '--capture', '--device', this._settings.get_string('camera-device')],
                message => {
                    if (message.event === 'ready') {
                        statusLabel.label = 'Look at the camera, with nobody else in view';
                        snapButton.sensitive = true;
                    } else if (message.event === 'frame') {
                        picture.set_paintable(Gdk.Texture.new_from_filename(message.path));
                    } else if (message.event === 'captured') {
                        capturedPath = message.path;
                    } else if (message.event === 'error') {
                        failure = message.message;
                    }
                },
                () => {
                    process = null;
                    if (closed) {
                        finish();
                    } else if (failure) {
                        statusLabel.label = failure;
                        snapButton.sensitive = false;
                    } else {
                        dialog.close(); // Its closed handler calls finish().
                    }
                });
        } catch (error) {
            statusLabel.label = `Can't start the daemon: ${error.message}`;
        }

        dialog.present(window);
    }

    /// --- SETTINGS GROUPS --- ///
    _spinRow(title, subtitle, key, lower, upper, step, digits, isDouble) {
        const row = new Adw.SpinRow({
            title,
            subtitle,
            digits,
            adjustment: new Gtk.Adjustment({lower, upper, step_increment: step}),
        });
        row.value = isDouble ? this._settings.get_double(key) : this._settings.get_int(key);
        this._settings.bind(key, row, 'value', Gio.SettingsBindFlags.DEFAULT);
        return row;
    }

    _buildCameraGroup() {
        const group = new Adw.PreferencesGroup({title: 'Camera'});

        const cameras = [{path: 'auto', name: 'Automatic'}];
        const current = this._settings.get_string('camera-device');
        const model = new Gtk.StringList({strings: [cameras[0].name]});
        const row = new Adw.ComboRow({title: 'Device', model});
        group.add(row);

        const addCamera = camera => {
            cameras.push(camera);
            model.append(camera.name);
        };
        if (current !== 'auto')
            addCamera({path: current, name: current});
        row.selected = current === 'auto' ? 0 : 1;
        row.connect('notify::selected', () => {
            const chosen = cameras[row.selected];
            if (chosen)
                this._settings.set_string('camera-device', chosen.path);
        });

        try {
            runDaemon([...this._daemonBase(), '--list-cameras'], message => {
                for (const camera of message.cameras ?? []) {
                    const label = camera.virtual ? `${camera.name} (virtual)` : camera.name;
                    const known = cameras.findIndex(c => c.path === camera.path);
                    if (known >= 0) {
                        cameras[known].name = label;
                        model.splice(known, 1, [label]);
                        row.selected = known;
                    } else {
                        addCamera({path: camera.path, name: label});
                    }
                }
            });
        } catch (error) {
            console.warn(`Face Guard: can't list cameras: ${error.message}`);
        }

        group.add(this._spinRow(
            'Snap interval',
            'Milliseconds between snaps. Can\'t go faster than the camera delivers frames.',
            'interval-ms', 1, 600000, 100, 0, false));
        return group;
    }

    _buildDetectionGroup() {
        const group = new Adw.PreferencesGroup({
            title: 'Recognition',
            description: 'The panel menu shows the live match score, to help you tune these.',
        });
        group.add(this._spinRow(
            'Match threshold',
            'How closely a face must match yours. Higher is stricter.',
            'match-threshold', 0.1, 0.95, 0.05, 2, true));
        group.add(this._spinRow(
            'Detection threshold',
            'How confident the detector must be that something is a face.',
            'detection-threshold', 0.1, 0.95, 0.05, 2, true));
        group.add(this._spinRow(
            'Smallest face',
            'Ignore faces smaller than this many pixels, such as people far away.',
            'min-face-px', 0, 1000, 5, 0, false));
        group.add(this._spinRow(
            'Lock after absence',
            'Seconds your face can be missing before the screen locks.',
            'absence-grace-s', 1, 600, 1, 1, true));
        return group;
    }

    _buildActionGroup() {
        const group = new Adw.PreferencesGroup({
            title: 'When someone else appears',
            description: 'Runs when another face is in view alongside yours.',
        });
        group.add(this._spinRow(
            'Delay',
            'Seconds the other face must stay in view first.',
            'intruder-grace-s', 0, 60, 0.5, 1, true));

        const action = new Adw.ComboRow({
            title: 'Action',
            model: new Gtk.StringList({strings: ACTIONS.map(([, label]) => label)}),
        });
        action.selected = Math.max(0, ACTIONS.findIndex(
            ([id]) => id === this._settings.get_string('intruder-action')));
        group.add(action);

        const command = new Adw.EntryRow({title: 'Command (run with sh -c)'});
        this._settings.bind('intruder-command', command, 'text', Gio.SettingsBindFlags.DEFAULT);
        group.add(command);

        const workspace = this._spinRow(
            'Workspace', 'Workspace number to move to.', 'intruder-workspace', 1, 36, 1, 0, false);
        group.add(workspace);

        const returnOnClear = new Adw.SwitchRow({title: 'Return once they\'ve gone'});
        this._settings.bind('return-on-clear', returnOnClear, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(returnOnClear);

        const syncVisible = () => {
            const id = ACTIONS[action.selected][0];
            command.visible = id === 'command';
            workspace.visible = id === 'workspace';
            returnOnClear.visible = id === 'workspace';
        };
        action.connect('notify::selected', () => {
            this._settings.set_string('intruder-action', ACTIONS[action.selected][0]);
            syncVisible();
        });
        syncVisible();
        return group;
    }

    /// --- APPS TO MINIMIZE --- ///
    _buildMinimizeGroup(window) {
        const group = new Adw.PreferencesGroup({
            title: 'Minimize apps',
            description: 'Also minimizes these apps\' windows when someone else appears, whatever the action above.',
        });
        const add = new Gtk.Button({
            icon_name: 'list-add-symbolic',
            tooltip_text: 'Add App',
            valign: Gtk.Align.CENTER,
            css_classes: ['flat'],
        });
        add.connect('clicked', () => this._openAppChooser(window));
        group.set_header_suffix(add);

        const restore = new Adw.SwitchRow({title: 'Restore once they\'ve gone'});
        this._settings.bind('minimize-restore', restore, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(restore);

        let rows = [];
        const refresh = () => {
            rows.forEach(row => group.remove(row));
            rows = this._settings.get_strv('minimize-apps').map(id => this._appRow(id));
            rows.forEach(row => group.add(row));
            restore.visible = rows.length > 0;
        };
        this._settings.connect('changed::minimize-apps', refresh);
        refresh();
        return group;
    }

    _appRow(id) {
        const info = Gio.DesktopAppInfo.new(id);
        const row = new Adw.ActionRow({
            title: GLib.markup_escape_text(info?.get_display_name() ?? id, -1),
            subtitle: info ? '' : 'Not installed',
        });
        row.add_prefix(new Gtk.Image({
            gicon: info?.get_icon() ?? Gio.ThemedIcon.new('application-x-executable'),
            pixel_size: 32,
        }));
        const remove = new Gtk.Button({
            icon_name: 'user-trash-symbolic',
            tooltip_text: 'Remove',
            valign: Gtk.Align.CENTER,
            css_classes: ['flat'],
        });
        remove.connect('clicked', () => this._settings.set_strv(
            'minimize-apps', this._settings.get_strv('minimize-apps').filter(other => other !== id)));
        row.add_suffix(remove);
        return row;
    }

    _openAppChooser(window) {
        const chosen = new Set(this._settings.get_strv('minimize-apps'));
        const apps = Gio.AppInfo.get_all()
            .filter(app => app.should_show() && app.get_id() && !chosen.has(app.get_id()))
            .sort((a, b) => a.get_display_name().localeCompare(b.get_display_name()));

        const search = new Gtk.SearchEntry({placeholder_text: 'Search apps', hexpand: true});
        const list = new Gtk.ListBox({
            selection_mode: Gtk.SelectionMode.NONE,
            css_classes: ['boxed-list'],
            margin_top: 12,
            margin_bottom: 12,
            margin_start: 12,
            margin_end: 12,
            valign: Gtk.Align.START,
        });
        const dialog = new Adw.Dialog({title: 'Add App', content_width: 420, content_height: 560});
        for (const app of apps) {
            const row = new Adw.ActionRow({
                title: GLib.markup_escape_text(app.get_display_name(), -1),
                activatable: true,
            });
            row.add_prefix(new Gtk.Image({
                gicon: app.get_icon() ?? Gio.ThemedIcon.new('application-x-executable'),
                pixel_size: 32,
            }));
            row._name = app.get_display_name().toLowerCase();
            row.connect('activated', () => {
                this._settings.set_strv('minimize-apps', [...chosen, app.get_id()]);
                dialog.close();
            });
            list.append(row);
        }
        list.set_filter_func(row => row._name.includes(search.text.toLowerCase()));
        search.connect('search-changed', () => list.invalidate_filter());

        const header = new Adw.HeaderBar({title_widget: search});
        const toolbar = new Adw.ToolbarView({
            content: new Gtk.ScrolledWindow({child: list, vexpand: true}),
        });
        toolbar.add_top_bar(header);
        dialog.child = toolbar;
        dialog.present(window);
        search.grab_focus();
    }

    _buildAdvancedGroup() {
        const group = new Adw.PreferencesGroup({title: 'Advanced'});
        const python = new Adw.EntryRow({title: 'Python with insightface installed'});
        this._settings.bind('python-path', python, 'text', Gio.SettingsBindFlags.DEFAULT);
        group.add(python);
        return group;
    }
}
