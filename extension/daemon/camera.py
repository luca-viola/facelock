"""Finding cameras and reading their newest frame. Listing and opening them is per platform."""

import collections
import sys
import threading
import time

from errors import GuardError

if sys.platform == "darwin":
    from camera_avfoundation import list_cameras, open_capture

    # macOS usually lets several apps use a camera at once, so nothing is handed over.
    # Untested with Facelock.
    CameraUsers = None
else:
    from camera_v4l2 import CameraUsers, list_cameras, open_capture

# Requested size; the camera driver may pick the nearest one it supports.
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
# The first frames after opening are often dark while auto-exposure settles, and
# must not count as "owner absent".
WARMUP_S = 1.5
FRAME_TIMEOUT_S = 5.0
CAMERA_OPEN_ATTEMPTS = 10
CAMERA_RETRY_S = 0.5


def resolve_device(device):
    """Turns "auto" into the first real camera, skipping virtual ones like OBS."""
    if device != "auto":
        return device
    for camera in list_cameras():
        if not camera["virtual"]:
            return camera["path"]
    raise GuardError("camera", "No physical camera found", retryable=True)


class Camera:
    """Keeps only the newest frame from a camera.

    A reader thread drains the driver continuously. Otherwise, with a long snap
    interval, a read would return a frame queued seconds ago. read() is served
    from the next frame to arrive, so nothing can be analyzed faster than the
    camera actually delivers, whatever framerate it claims.
    """

    def __init__(self, device):
        self._capture = open_capture(device, FRAME_WIDTH, FRAME_HEIGHT)
        self.device = device
        self._device = device
        self._want_frame = False
        self._frame = None
        self._failed = False
        self._stop = False
        self._frame_ready = threading.Event()
        self._grab_times = collections.deque(maxlen=30)
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self):
        while not self._stop:
            if not self._capture.grab():
                self._failed = True
                self._frame_ready.set()
                return
            self._grab_times.append(time.monotonic())
            if self._want_frame:
                self._want_frame = False
                ok, frame = self._capture.retrieve()
                self._frame = frame if ok else None
                self._failed = not ok
                self._frame_ready.set()

    def read(self, timeout=FRAME_TIMEOUT_S):
        self._frame_ready.clear()
        self._want_frame = True
        if not self._frame_ready.wait(timeout):
            raise GuardError("camera", f"Camera {self._device} stopped sending frames", retryable=True)
        if self._failed or self._frame is None:
            raise GuardError("camera", f"Camera {self._device} failed or is in use", retryable=True)
        return self._frame

    def measured_fps(self):
        times = self._grab_times
        if len(times) < 2 or times[-1] <= times[0]:
            return 0.0
        return (len(times) - 1) / (times[-1] - times[0])

    def close(self):
        self._stop = True
        self._thread.join(timeout=FRAME_TIMEOUT_S)
        if not self._thread.is_alive():
            self._capture.release()


def open_camera(device):
    """Opens a camera, waiting out a previous owner that is still releasing it."""
    last_error = None
    for _ in range(CAMERA_OPEN_ATTEMPTS):
        camera = None
        try:
            camera = Camera(resolve_device(device))
            camera.read()
            return camera
        except GuardError as error:
            last_error = error
            if camera:
                camera.close()
            time.sleep(CAMERA_RETRY_S)
    raise last_error


def watch_camera_users(device_path):
    """A CameraUsers for this camera, or None where cameras are shared or it can't be watched."""
    if CameraUsers is None:
        return None
    try:
        return CameraUsers(device_path)
    except OSError as error:
        import logging

        logging.getLogger("facelock").warning("Can't watch for other apps using the camera: %s", error)
        return None
