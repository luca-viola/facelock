"""Finding Video4Linux cameras and reading their newest frame."""

import collections
import fcntl
import os
import struct
import threading
import time

from errors import GuardError

# Requested size; the camera driver may pick the nearest one it supports.
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
# The first frames after opening are often dark while auto-exposure settles, and
# must not count as "owner absent".
WARMUP_S = 1.5
FRAME_TIMEOUT_S = 5.0
CAMERA_OPEN_ATTEMPTS = 10
CAMERA_RETRY_S = 0.5

VIDIOC_QUERYCAP = 0x80685600
V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_DEVICE_CAPS = 0x80000000
V4L2_LOOPBACK_DRIVER = "v4l2 loopback"
BY_ID_DIR = "/dev/v4l/by-id"


def query_camera(path):
    """Returns (card name, driver) for a capture device, or None for anything else."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        raw = fcntl.ioctl(fd, VIDIOC_QUERYCAP, bytes(104))
    except OSError:
        return None
    finally:
        os.close(fd)
    driver, card, _bus, _version, caps, device_caps = struct.unpack("16s32s32sIII", raw[:92])
    effective = device_caps if caps & V4L2_CAP_DEVICE_CAPS else caps
    if not effective & V4L2_CAP_VIDEO_CAPTURE:
        return None
    decode = lambda value: value.split(b"\0", 1)[0].decode("utf-8", "replace")
    return decode(card), decode(driver)


def stable_paths():
    """Maps /dev/videoN to its /dev/v4l/by-id name, which survives replugging."""
    paths = {}
    try:
        names = sorted(os.listdir(BY_ID_DIR))
    except OSError:
        return paths
    for name in names:
        link = os.path.join(BY_ID_DIR, name)
        paths.setdefault(os.path.realpath(link), link)
    return paths


def list_cameras():
    stable = stable_paths()
    numbered = []
    for name in os.listdir("/dev"):
        if name.startswith("video") and name[5:].isdigit():
            numbered.append(int(name[5:]))
    cameras = []
    for number in sorted(numbered):
        node = f"/dev/video{number}"
        info = query_camera(node)
        if info:
            cameras.append({
                "path": stable.get(node, node),
                "name": info[0],
                "virtual": info[1] == V4L2_LOOPBACK_DRIVER,
            })
    return cameras


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
        import cv2

        self._cv2 = cv2
        self._capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self._capture.isOpened():
            self._capture.release()
            raise GuardError("camera", f"Can't open camera {device}", retryable=True)
        self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
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
