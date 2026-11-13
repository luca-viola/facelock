"""Carries out what a trigger from the daemon asks for."""

import logging
import os
import subprocess
import threading

from PyObjCTools import AppHelper
from AppKit import NSBundle, NSRunningApplication, NSWorkspace

from eyes import Eyes
from lock import lock_screen

log = logging.getLogger("faceguard")


class Actions:
    """notify(title, message) shows a notification. set_tracking(True) asks the daemon to
    snap at full speed, for the eyes to follow."""

    def __init__(self, settings, set_tracking, notify):
        self._settings = settings
        self._set_tracking = set_tracking
        self._notify = notify
        self._eyes = None
        self._intruder_at = (0.5, 0.5)
        self._finder_collapsed = False
        self._hidden = []  # bundle identifiers of the apps hidden by an intruder

    def destroy(self):
        """Leaves hidden apps hidden, which is the safe side after a lock."""
        self.close_eyes()
        self._hidden.clear()

    def lock(self):
        try:
            lock_screen()
        except (OSError, subprocess.SubprocessError) as error:
            self._notify("Face Guard", f"Can't lock the screen: {error}")

    def intruder(self, other_faces):
        self._hide_apps()
        action = self._settings.get("intruder-action")
        if action == "lock":
            self.lock()
        elif action == "command":
            self._run_command(other_faces)
        elif action == "notify":
            self._notify("Face Guard", "Someone else is looking at your screen.")
        elif action == "eyes":
            self._show_eyes()

    def intruder_at(self, x, y):
        """Where the other face is in the camera image, from 0 to 1 on each axis."""
        self._intruder_at = (x, y)
        if self._eyes:
            self._eyes.look_at(x, y)

    def close_eyes(self):
        if not self._eyes:
            return
        self._eyes.destroy()
        self._eyes = None
        self._set_tracking(False)

    def clear(self):
        """The other face left."""
        self.close_eyes()
        self._restore_apps()

    # Dismissing only closes the eyes. They come back because the daemon triggers
    # once per episode, so the next trigger means the face left and returned.
    def _show_eyes(self):
        if self._eyes:
            return
        self._eyes = Eyes(self.close_eyes)
        self._eyes.look_at(*self._intruder_at)
        self._set_tracking(True)

    def _apps_to_hide(self):
        """Bundle identifiers of the chosen apps, or of every open app with a Dock icon
        (except Face Guard) when "all open apps" is on."""
        chosen = list(self._settings.get("minimize-apps"))
        if not self._settings.get("minimize-all"):
            return chosen
        # Finder can't be hidden, and hiding by identifier would also hide this app.
        skip = {"com.apple.finder", str(NSBundle.mainBundle().bundleIdentifier())}
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            bundle_id = app.bundleIdentifier()
            if (app.activationPolicy() == 0 and bundle_id and str(bundle_id) not in skip
                    and str(bundle_id) not in chosen):
                chosen.append(str(bundle_id))
        return chosen

    # Hides the chosen apps, remembering which ones this did so they can be shown
    # again. A failure mustn't stop the main action.
    def _hide_apps(self):
        for bundle_id in self._apps_to_hide():
            for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id):
                if app.isHidden():
                    continue
                app.hide()  # returns False even when it works, because it only asks
                if bundle_id not in self._hidden:
                    self._hidden.append(bundle_id)
        if self._settings.get("minimize-all"):
            self._finder_windows(True)
        self._through_system_events(self._hidden, visible=False)

    def _through_system_events(self, bundle_ids, visible):
        """Hides or shows every one of these apps through System Events as well, on top of the
        normal request. Some apps, such as Edge, ignore hide() and unhide() but obey this, and
        doing it for all of them means no app has to be singled out. Needs the Automation
        permission for System Events, which macOS asks for."""
        if not bundle_ids:
            return
        script = ('on run argv\nset wanted to (item 1 of argv) is "true"\n'
                  'tell application "System Events"\nrepeat with bundleId in (rest of argv)\n'
                  'try\nset visible of (every process whose bundle identifier is bundleId) to wanted\nend try\n'
                  'end repeat\nend tell\nend run')
        ids = list(bundle_ids)

        def run():
            try:
                result = subprocess.run(["/usr/bin/osascript", "-e", script, str(visible).lower(), *ids],
                                        capture_output=True, text=True, timeout=30)
            except subprocess.SubprocessError as error:
                log.warning("System Events didn't answer: %s", error)
                return
            if result.returncode:
                log.warning("System Events couldn't change the apps: %s", result.stderr.strip())

        threading.Thread(target=run, daemon=True).start()

    def _finder_windows(self, minimize):
        """Finder can't be hidden, so its windows are minimized. Needs the Automation
        permission for Finder, which macOS asks for the first time."""
        if minimize:
            script = ('tell application "Finder"\nif (count of windows) is 0 then return "none"\n'
                      'set collapsed of every window to true\nreturn "done"\nend tell')
        elif self._finder_collapsed:
            script = 'tell application "Finder" to set collapsed of every window to false'
        else:
            return

        def run():
            try:
                result = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True,
                                        timeout=10)
            except subprocess.SubprocessError:
                return
            if minimize and result.stdout.strip() == "done":
                self._finder_collapsed = True
            elif not minimize:
                self._finder_collapsed = False

        threading.Thread(target=run, daemon=True).start()

    def _restore_apps(self):
        hidden, self._hidden = self._hidden, []
        if not self._settings.get("minimize-restore"):
            self._finder_collapsed = False
            return
        self._finder_windows(False)
        for bundle_id in hidden:
            for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id):
                if app.isHidden():  # not if the user has already brought it back
                    app.unhide()
        self._through_system_events(hidden, visible=True)

    def _run_command(self, other_faces):
        command = self._settings.get("intruder-command").strip()
        if not command:
            self._notify("Face Guard", "Another face appeared, but no command is configured.")
            return
        try:
            process = subprocess.Popen(
                ["/bin/sh", "-c", command], cwd=os.path.expanduser("~"), stderr=subprocess.PIPE, text=True,
                env={**os.environ, "FACEGUARD_OTHER_FACES": str(other_faces)})
        except OSError as error:
            self._notify("Face Guard", f"Can't run the command: {error}")
            return

        def wait():
            _out, err = process.communicate()
            if process.returncode:
                AppHelper.callAfter(self._notify, "Face Guard",
                                    f"The command failed ({process.returncode}): {err.strip()[:200]}")

        threading.Thread(target=wait, daemon=True).start()
