"""Runs the Python daemon and reports its JSON-line events on the main thread."""

import json
import logging
import subprocess
import threading

from PyObjCTools import AppHelper

log = logging.getLogger("faceguard")

EXIT_FATAL = 4  # the daemon's "restarting won't help" exit code
STOP_WAIT_S = 3


class DaemonClient:
    """Starts the daemon with argv. on_event(message) and on_exit(status) run on the main thread."""

    def __init__(self, argv, on_event, on_exit, log_file=None):
        self._on_event = on_event
        self._on_exit = on_exit
        self._stopped = False
        self._process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log_file or subprocess.DEVNULL,
            text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self._process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                log.warning("Ignoring bad daemon output: %s", line.strip())
                continue
            if not self._stopped:
                AppHelper.callAfter(self._on_event, message)
        status = self._process.wait()
        if not self._stopped:
            AppHelper.callAfter(self._on_exit, status)

    def send(self, line):
        """Sends one command line. The daemon may have just exited, which is fine."""
        try:
            self._process.stdin.write(f"{line}\n")
            self._process.stdin.flush()
        except (OSError, ValueError):
            log.warning("Can't send %r to the daemon", line)

    def stop(self):
        """Ends the daemon without calling on_exit. Closing stdin lets it clean up first."""
        self._stopped = True
        try:
            self._process.stdin.close()
        except OSError:
            pass
        try:
            self._process.wait(timeout=STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            self._process.kill()


def run_once(argv, on_message, on_done=None):
    """Runs a one-shot daemon mode in the background, such as --list-cameras.

    on_message(message) runs on the main thread for every event. on_done(status) runs after it exits.
    """
    def work():
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError as error:
            AppHelper.callAfter(on_message, {"event": "error", "message": str(error), "retryable": False})
            return
        for line in process.stdout:
            try:
                AppHelper.callAfter(on_message, json.loads(line))
            except ValueError:
                pass
        status = process.wait()
        if on_done:
            AppHelper.callAfter(on_done, status)

    threading.Thread(target=work, daemon=True).start()
