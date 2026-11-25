#!/usr/bin/env python3
"""Face Guard for macOS: a menu bar app that runs the camera and face-recognition daemon.

It does what the GNOME Shell extension does, with the same daemon: it starts it, keeps it
running, and carries out the actions it asks for.
"""

import logging
import os
import sys
import threading

import rumps
from AppKit import (NSDistributedNotificationCenter, NSObject, NSRunningApplication, NSWorkspace,
                    NSWorkspaceDidWakeNotification, NSWorkspaceScreensDidSleepNotification,
                    NSWorkspaceScreensDidWakeNotification, NSWorkspaceWillSleepNotification)
from PyObjCTools import AppHelper

import permissions
import ui
from actions import Actions
from daemon_client import EXIT_FATAL, DaemonClient, run_once
from reference_window import ReferenceWindow
from settings import REFERENCE_PATH, RESTART_KEYS, Settings

log = logging.getLogger("faceguard")

RESTART_DEBOUNCE_S = 0.8  # menu choices can change quickly
BACKOFF_MIN_S = 2
BACKOFF_MAX_S = 60
LOG_PATH = os.path.expanduser("~/Library/Logs/FaceGuard.log")
HERE = os.path.dirname(os.path.abspath(__file__))
THRESHOLDS = (0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6)

# SF Symbols for the menu bar icon.
ICONS = {
    "off": ("eye.slash", "Not watching"),
    "starting": ("eye", "Starting"),
    "owner": ("checkmark.shield", "You're here"),
    "absent": ("exclamationmark.shield", "You're not recognized"),
    "intruder": ("person.2", "Someone else is looking"),
    "error": ("exclamationmark.triangle", "Face Guard isn't watching"),
}


def daemon_script():
    """The daemon is shared with the GNOME extension, so in a checkout it's in ../extension."""
    for folder in (os.environ.get("RESOURCEPATH"), os.path.join(HERE, "..", "extension")):
        if folder:
            path = os.path.join(folder, "daemon", "facelock_daemon.py")
            if os.path.exists(path):
                return os.path.abspath(path)
    raise FileNotFoundError("facelock_daemon.py")


def _clear(menu):
    """rumps can only clear a menu item that already has a submenu."""
    if menu._menu is not None:
        menu.clear()


class Delay:
    """One cancellable delayed call on the main thread."""

    def __init__(self):
        self._token = 0
        self._timer = None

    def start(self, seconds, function):
        self.cancel()
        token = self._token

        def fire():
            if token == self._token:
                function()

        self._timer = threading.Timer(seconds, lambda: AppHelper.callAfter(fire))
        self._timer.daemon = True
        self._timer.start()

    def cancel(self):
        self._token += 1
        if self._timer:
            self._timer.cancel()
            self._timer = None


class SystemObserver(NSObject):
    """Tells when the screen locks or sleeps. The camera is off for as long as it does."""

    def initWithOnChange_(self, on_change):
        self = self.init()
        self._on_change = on_change
        center = NSDistributedNotificationCenter.defaultCenter()
        for name, selector in (("com.apple.screenIsLocked", "locked:"), ("com.apple.screenIsUnlocked", "unlocked:")):
            center.addObserver_selector_name_object_(self, selector, name, None)
        workspace = NSWorkspace.sharedWorkspace().notificationCenter()
        for name, selector in ((NSWorkspaceScreensDidSleepNotification, "displayAsleep:"),
                               (NSWorkspaceScreensDidWakeNotification, "displayAwake:"),
                               (NSWorkspaceWillSleepNotification, "systemAsleep:"),
                               (NSWorkspaceDidWakeNotification, "systemAwake:")):
            workspace.addObserver_selector_name_object_(self, selector, name, None)
        return self

    def locked_(self, _n): self._on_change("locked", True)
    def unlocked_(self, _n): self._on_change("locked", False)
    def displayAsleep_(self, _n): self._on_change("display asleep", True)
    def displayAwake_(self, _n): self._on_change("display asleep", False)
    def systemAsleep_(self, _n): self._on_change("system asleep", True)
    def systemAwake_(self, _n): self._on_change("system asleep", False)


class FaceGuard:
    def __init__(self):
        self.settings = Settings()
        self.settings.on_change(self._on_setting)
        self.actions = Actions(self.settings, self._set_tracking, ui.notify)
        self._daemon = None
        self._paused_for = set()
        self._running = ""
        self._last_error = None
        self._gpu_warned = False
        self._backoff_s = BACKOFF_MIN_S
        self._restart = Delay()
        self._debounce = Delay()
        self._enrolling = False
        self._capture = None
        self._capture_window = None
        self._cameras = []
        self._models = []
        self._choices = []
        self._log_file = open(LOG_PATH, "a")

        self.app = rumps.App("Face Guard", quit_button=None)
        self._build_menu()
        self._observer = SystemObserver.alloc().initWithOnChange_(self._on_system)
        self._starter = rumps.Timer(self._late_start, 0.2)
        self._starter.start()

    # Menu

    def _build_menu(self):
        self._status_item = rumps.MenuItem("Not watching")
        self._detail_item = rumps.MenuItem("")
        self._watch_item = rumps.MenuItem("Watch camera", callback=self._toggle_watch)
        self._camera_menu = rumps.MenuItem("Camera")
        self._model_menu = rumps.MenuItem("Model")
        self._gpu_item = rumps.MenuItem("Use Apple GPU (CoreML)", callback=self._toggle_gpu)
        self._threshold_menu = rumps.MenuItem("Match threshold")
        self._apps_menu = rumps.MenuItem("Hide apps when someone else looks")
        self._command_item = rumps.MenuItem("Set Command…", callback=self._set_command)

        for label, value in (("Default for this model", None), *((f"{t:.2f}", t) for t in THRESHOLDS)):
            item = rumps.MenuItem(label, callback=lambda _s, v=value: self._set_threshold(v))
            self._threshold_menu.add(item)
        self._threshold_items = list(self._threshold_menu.values())
        self._threshold_values = [None, *THRESHOLDS]

        action_menu = self._choice_menu("When someone else looks", "intruder-action", (
            ("Lock the screen", "lock"), ("Show giant eyes", "eyes"),
            ("Notify me", "notify"), ("Run a command", "command")))
        action_menu.add(None)
        action_menu.add(self._command_item)
        timing = rumps.MenuItem("Timing")
        timing.add(self._choice_menu("Snap every", "interval-ms", (
            ("0.5 s", 500), ("1 s", 1000), ("2 s", 2000), ("5 s", 5000))))
        timing.add(self._choice_menu("Lock when you're gone for", "absence-grace-s", (
            ("5 s", 5.0), ("10 s", 10.0), ("20 s", 20.0), ("30 s", 30.0), ("60 s", 60.0))))
        timing.add(self._choice_menu("React to another face after", "intruder-grace-s", (
            ("0.5 s", 0.5), ("1 s", 1.0), ("2 s", 2.0), ("5 s", 5.0))))
        restore = rumps.MenuItem("Show hidden apps when they leave", callback=self._toggle_restore)
        self._restore_item = restore

        settings = rumps.MenuItem("Settings")
        for item in (self._camera_menu, self._model_menu, self._gpu_item, self._threshold_menu, timing, None,
                     action_menu, self._apps_menu, restore, None,
                     rumps.MenuItem("Camera Privacy Settings…", callback=lambda _s: permissions.open_camera_settings()),
                     rumps.MenuItem("Show Log…", callback=lambda _s: os.system(f"open -a Console '{LOG_PATH}'"))):
            settings.add(item)

        self.app.menu = [
            self._status_item, self._detail_item, None,
            self._watch_item,
            rumps.MenuItem("Take Reference Photo…", callback=lambda _s: self.take_reference()),
            rumps.MenuItem("Choose Reference File…", callback=lambda _s: self.choose_reference()),
            None, settings, None,
            rumps.MenuItem("Quit Face Guard", callback=self._quit),
        ]
        self._refresh_menu()

    def _choice_menu(self, title, key, options):
        menu = rumps.MenuItem(title)
        items = {}
        for label, value in options:
            item = rumps.MenuItem(label, callback=lambda _s, v=value: self.settings.set(key, v))
            menu.add(item)
            items[value] = item
        self._choices.append((key, items))
        return menu

    def _refresh_menu(self):
        s = self.settings
        self._watch_item.state = int(s.get("enabled"))
        self._restore_item.state = int(s.get("minimize-restore"))
        self._gpu_item.state = int(s.get("use-gpu"))
        self._command_item.title = "Set Command…" if not s.get("intruder-command") else \
            f"Command: {s.get('intruder-command')[:40]}…"
        for key, items in self._choices:
            for value, item in items.items():
                item.state = int(s.get(key) == value)
        current = s.get("match-thresholds").get(s.get("model"))
        for value, item in zip(self._threshold_values, self._threshold_items):
            item.state = int(value == current)

    def _set_status(self, key, text):
        first, _, rest = text.partition("\n")
        self._status_item.title = first
        self._detail_item.title = rest
        # The status item doesn't exist until the app runs.
        status_item = getattr(getattr(self.app, "_nsapp", None), "nsstatusitem", None)
        button = status_item.button() if status_item else None
        if button is not None:
            name, description = ICONS[key]
            image = ui.symbol(name, description)
            if image is not None:
                button.setImage_(image)
                button.setTitle_("")
            else:
                button.setTitle_("Face Guard")

    def _late_start(self, timer):
        timer.stop()
        self._set_status("off", "Not watching")
        self._load_cameras()
        self._load_models()
        self._rebuild_apps_menu()
        self._sync()

    # Camera and model lists, which only the daemon's Python can produce

    def _load_cameras(self):
        def on_message(message):
            if message.get("event") == "cameras":
                self._cameras = message["cameras"]
                self._rebuild_camera_menu()

        run_once(self._daemon_command("--list-cameras"), on_message)

    def _rebuild_camera_menu(self):
        _clear(self._camera_menu)
        entries = [("Automatic", "auto"), *((c["name"] + (" (virtual)" if c["virtual"] else ""), c["path"])
                                            for c in self._cameras)]
        items = {}
        for label, path in entries:
            item = rumps.MenuItem(label, callback=lambda _s, p=path: self.settings.set("camera-device", p))
            self._camera_menu.add(item)
            items[path] = item
        self._camera_menu.add(None)
        self._camera_menu.add(rumps.MenuItem("Refresh", callback=lambda _s: self._load_cameras()))
        self._choices = [c for c in self._choices if c[0] != "camera-device"]
        self._choices.append(("camera-device", items))
        self._refresh_menu()

    def _load_models(self):
        def on_message(message):
            if message.get("event") == "models":
                self._models = [m for m in message["models"] if m["installed"]]
                self._rebuild_model_menu()

        run_once(self._daemon_command("--list-models"), on_message)

    def _rebuild_model_menu(self):
        _clear(self._model_menu)
        items = {}
        for model in self._models:
            label = model["label"] + ("" if model["downloaded"] else " (downloads when first used)")
            item = rumps.MenuItem(label, callback=lambda _s, m=model["id"]: self.settings.set("model", m))
            self._model_menu.add(item)
            items[model["id"]] = item
        self._choices = [c for c in self._choices if c[0] != "model"]
        self._choices.append(("model", items))
        self._refresh_menu()
        self._update_gpu_item()

    def _update_gpu_item(self):
        model = next((m for m in self._models if m["id"] == self.settings.get("model")), None)
        # Greyed out when there's nothing to click it with.
        self._gpu_item.set_callback(self._toggle_gpu if model and model["gpu"] else None)

    def _rebuild_apps_menu(self):
        _clear(self._apps_menu)
        all_item = rumps.MenuItem("All open apps", callback=self._toggle_all_apps)
        all_item.state = int(self.settings.get("minimize-all"))
        self._apps_menu.add(all_item)
        self._apps_menu.add(None)
        chosen = list(self.settings.get("minimize-apps"))
        names = {}
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.activationPolicy() == 0 and app.bundleIdentifier():  # regular apps, with a Dock icon
                names[str(app.bundleIdentifier())] = str(app.localizedName())
        for bundle_id in chosen:
            names.setdefault(bundle_id, bundle_id)
        for bundle_id, name in sorted(names.items(), key=lambda kv: kv[1].lower()):
            if bundle_id == "com.apple.finder":
                continue
            item = rumps.MenuItem(name, callback=lambda s, b=bundle_id: self._toggle_app(b))
            item.state = int(bundle_id in chosen)
            self._apps_menu.add(item)
        self._apps_menu.add(None)
        self._apps_menu.add(rumps.MenuItem("Refresh", callback=lambda _s: self._rebuild_apps_menu()))

    # Menu actions

    def _toggle_watch(self, _sender):
        self.settings.set("enabled", not self.settings.get("enabled"))

    def _toggle_gpu(self, _sender):
        self.settings.set("use-gpu", not self.settings.get("use-gpu"))

    def _toggle_restore(self, _sender):
        self.settings.set("minimize-restore", not self.settings.get("minimize-restore"))

    def _toggle_all_apps(self, _sender):
        self.settings.set("minimize-all", not self.settings.get("minimize-all"))
        self._rebuild_apps_menu()

    def _toggle_app(self, bundle_id):
        chosen = list(self.settings.get("minimize-apps"))
        chosen.remove(bundle_id) if bundle_id in chosen else chosen.append(bundle_id)
        self.settings.set("minimize-apps", chosen)
        self._rebuild_apps_menu()

    def _set_threshold(self, value):
        thresholds = dict(self.settings.get("match-thresholds"))
        if value is None:
            thresholds.pop(self.settings.get("model"), None)
        else:
            thresholds[self.settings.get("model")] = value
        self.settings.set("match-thresholds", thresholds)

    def _set_command(self, _sender):
        window = rumps.Window("Runs through /bin/sh when another face appears. "
                              "FACEGUARD_OTHER_FACES holds how many.", "Command",
                              default_text=self.settings.get("intruder-command"), dimensions=(320, 24))
        response = window.run()
        if response.clicked:
            self.settings.set("intruder-command", response.text.strip())

    def _quit(self, _sender):
        self.shutdown()
        rumps.quit_application()

    def shutdown(self):
        self._restart.cancel()
        self._debounce.cancel()
        self._stop_daemon()
        self._close_capture()
        self.actions.destroy()

    # Settings and system events

    def _on_setting(self, key):
        self._refresh_menu()
        if key == "enabled":
            self._backoff_s = BACKOFF_MIN_S
            self._sync()
        elif key in RESTART_KEYS:
            self._debounce.start(RESTART_DEBOUNCE_S, self._restart_now)
        if key == "model":
            self._update_gpu_item()

    def _restart_now(self):
        self._backoff_s = BACKOFF_MIN_S
        self._sync()

    def _on_system(self, reason, paused):
        (self._paused_for.add if paused else self._paused_for.discard)(reason)
        self._backoff_s = BACKOFF_MIN_S
        self._sync()

    # The daemon

    def _python(self):
        return self.settings.get("python-path") or os.environ.get("FACEGUARD_PYTHON") or sys.executable

    def _daemon_command(self, *args):
        return [self._python(), daemon_script(), *args]

    def _model_args(self):
        s = self.settings
        return ["--model", s.get("model"), "--compute", "gpu" if s.get("use-gpu") else "cpu",
                "--detection-threshold", str(s.get("detection-threshold"))]

    def _daemon_argv(self):
        s = self.settings
        threshold = s.get("match-thresholds").get(s.get("model"))
        return self._daemon_command(
            "--reference", REFERENCE_PATH, "--device", s.get("camera-device"),
            "--interval-ms", str(s.get("interval-ms")), "--min-face-px", str(s.get("min-face-px")),
            "--absence-grace", str(s.get("absence-grace-s")), "--intruder-grace", str(s.get("intruder-grace-s")),
            *self._model_args(),
            # Without one set for this model, the daemon uses the model's own default.
            *([] if threshold is None else ["--match-threshold", str(threshold)]))

    def _set_tracking(self, on):
        if self._daemon:
            self._daemon.send("track" if on else "untrack")

    def _sync(self):
        """Starts or stops the daemon to match the settings, and shows why if it's off."""
        self._restart.cancel()
        self._stop_daemon()
        if not self.settings.get("enabled"):
            return self._set_status("off", "Not watching")
        if self._enrolling:
            return self._set_status("off", "Paused while taking a reference photo")
        if self._paused_for:
            return self._set_status("off", f"Paused: {sorted(self._paused_for)[0]}")
        if not os.path.exists(REFERENCE_PATH):
            return self._show_error("Set a reference image first")
        status = permissions.camera_status()
        if status in ("denied", "restricted"):
            return self._show_error("Camera access is off. Allow it in Settings, Camera Privacy Settings")
        if status == "undetermined":
            self._set_status("starting", "Waiting for camera permission…")
            permissions.request_camera_access(lambda _granted: AppHelper.callAfter(self._sync))
            return
        self._set_status("starting", "Starting…")
        try:
            self._daemon = DaemonClient(self._daemon_argv(), self._on_event, self._on_exit, self._log_file)
        except (OSError, FileNotFoundError) as error:
            self._show_error(f"Can't start the daemon: {error}")

    def _stop_daemon(self):
        # Also closes the eyes, because a stopped daemon can't say the face has gone.
        self.actions.close_eyes()
        if self._daemon:
            self._daemon.stop()
            self._daemon = None

    def _on_event(self, message):
        event = message.get("event")
        if event == "loading":
            self._set_status("starting", message["detail"])
        elif event == "ready":
            self._last_error = None
            self._backoff_s = BACKOFF_MIN_S
            self._running = f"{message['model']} on the {message['compute'].upper()}"
            self._set_status("starting", f"Watching with {self._running}")
            if message["requested"] == "gpu" and message["compute"] == "cpu" and not self._gpu_warned:
                self._gpu_warned = True
                ui.notify("Face Guard is running on the CPU", "Use GPU is on, but the GPU couldn't be used.")
        elif event == "status":
            self._show_status(message)
        elif event == "intruder_at":
            self.actions.intruder_at(message["x"], message["y"])
        elif event == "trigger":
            self._on_trigger(message)
        elif event == "error":
            self._show_error(message["message"])

    def _show_status(self, message):
        score = message["score"]
        match = "no face seen" if score is None else f"match {score:.2f}"
        speed = f"{message['snap_rate']:.1f} snaps/s, camera {message['camera_fps']:.0f} fps · {self._running}"
        others = message["others"]
        summary = {
            "owner": "You're here",
            "absent": "You're not recognized",
            "intruder": f"You and {others} other{'s' if others > 1 else ''}",
        }[message["state"]]
        self._set_status(message["state"], f"{summary} · {match}\n{speed}")

    def _on_trigger(self, message):
        kind = message["kind"]
        try:
            if kind == "absent":
                self.actions.lock()
            elif kind == "intruder":
                self.actions.intruder(message["others"])
            elif kind == "clear":
                self.actions.clear()
        except Exception as error:  # an action's failure mustn't take the app down
            log.exception("The %s action failed", kind)
            ui.notify("Face Guard", f"The {kind} action failed: {error}")

    def _on_exit(self, status):
        self._daemon = None
        self.actions.close_eyes()
        if status == EXIT_FATAL:
            return
        # While this is retrying nothing is being watched, so _show_error has already
        # told the user. Keep trying in case the camera comes back.
        self._set_status("error", f"{self._last_error or 'The daemon stopped'}. Retrying…")
        self._restart.start(self._backoff_s, self._sync)
        self._backoff_s = min(self._backoff_s * 2, BACKOFF_MAX_S)

    def _show_error(self, text):
        """Notifies once per distinct problem, because a menu bar icon is easy to miss."""
        self._set_status("error", text)
        if text != self._last_error:
            ui.notify("Face Guard isn't watching", text)
        self._last_error = text

    # The reference photo

    def choose_reference(self):
        path = ui.choose_image()
        if path:
            self._enroll(path, delete_after=False)

    def take_reference(self):
        if self._enrolling:
            return
        status = permissions.camera_status()
        if status in ("denied", "restricted"):
            ui.alert("Camera access is off", "Allow Face Guard in System Settings, Privacy & Security, Camera.")
            return permissions.open_camera_settings()
        self._enrolling = True
        self._sync()  # the camera has one user at a time
        self._capture_window = ReferenceWindow(lambda: self._capture and self._capture.send("snap"),
                                               self._cancel_capture)
        self._capture_window.show()
        try:
            self._capture = DaemonClient(
                self._daemon_command("--capture", "--device", self.settings.get("camera-device")),
                self._on_capture_event, lambda _status: self._capture_failed("The camera stopped."),
                self._log_file)
        except (OSError, FileNotFoundError) as error:
            self._capture_failed(f"Can't start the daemon: {error}")

    def _on_capture_event(self, message):
        event = message.get("event")
        window = self._capture_window
        if event == "ready":
            window.ready()
        elif event == "frame":
            window.show_frame(message["path"])
        elif event == "captured":
            path = message["path"]
            window.busy("Checking the photo…")
            self._close_capture(keep_window=True)
            self._enroll(path, delete_after=True)
        elif event == "error":
            self._capture_failed(message["message"])

    def _capture_failed(self, text):
        self._close_capture()
        self._enrolling = False
        ui.alert("Couldn't take the photo", text)
        self._sync()

    def _cancel_capture(self):
        self._close_capture(keep_window=True)
        self._enrolling = False
        self._sync()

    def _close_capture(self, keep_window=False):
        if self._capture:
            self._capture.stop()
            self._capture = None
        if self._capture_window and not keep_window:
            self._capture_window.close()
            self._capture_window = None

    def _enroll(self, path, delete_after):
        self._enrolling = True
        self._sync()
        outcome = {}

        def on_message(message):
            outcome.update(message)

        def on_done(_status):
            if delete_after and os.path.exists(path):
                os.remove(path)
            if self._capture_window:
                self._capture_window.close()
                self._capture_window = None
            self._enrolling = False
            if outcome.get("event") == "enrolled":
                ui.notify("Reference photo saved", "Face Guard will recognize you from this photo.")
            else:
                ui.alert("Couldn't use that photo", outcome.get("message", "The daemon stopped without a reason."))
            self._sync()

        run_once(self._daemon_command("--enroll", path, "--reference", REFERENCE_PATH, *self._model_args()),
                 on_message, on_done)

    def run(self):
        self.app.run()


def main():
    logging.basicConfig(level=logging.INFO, format="faceguard: %(message)s")
    FaceGuard().run()


if __name__ == "__main__":
    main()
