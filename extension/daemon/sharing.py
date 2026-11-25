"""Letting go of the camera while another app wants it, and taking it back afterwards.

On Linux a camera streams to one process at a time, so a video call can't start while
Facelock holds it. Facelock notices the other app opening the camera, closes it,
and reopens it once nobody else has held it for a while. The other app's first
attempt usually fails anyway, because it starts streaming within microseconds of
opening, so after an attempt like that Facelock waits longer, for the retry.
"""

import time

# Quiet time before taking the camera back, after an app used it.
RESUME_AFTER_USE_S = 3.0
# After an app opened it without keeping it, as when its first attempt failed:
# long enough to click the call's camera button again.
RESUME_AFTER_ATTEMPT_S = 15.0
CHECK_PERIOD_S = 1.0


class CameraSharing:
    def __init__(self, users, open_camera, emit, clock=time.monotonic):
        self._users = users
        self._open_camera = open_camera
        self._emit = emit
        self._clock = clock

    def started(self):
        """Call after opening the camera, so the opens it caused aren't taken for another app."""
        self._users.forget_own_opens()

    def check(self, camera):
        """Returns the camera to use: this one, or a reopened one after another app used it."""
        if not self._users.opened_since_last_check():
            return camera
        camera.close()
        self._emit("paused", apps=sorted(set(self._users.holders())))
        self._wait_until_free()
        camera = self._open_camera()
        self.started()
        self._emit("resumed")
        return camera

    def _wait_until_free(self):
        held = False
        free_since = None  # when the camera was first seen free, after anyone last held it
        while True:
            if self._users.holders():
                held = True
                free_since = None
            else:
                now = self._clock()
                if free_since is None:
                    free_since = now
                if now - free_since >= (RESUME_AFTER_USE_S if held else RESUME_AFTER_ATTEMPT_S):
                    return
            self._users.wait_for_change(CHECK_PERIOD_S)
