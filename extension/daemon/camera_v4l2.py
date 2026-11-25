"""Video4Linux cameras: finding them and opening one."""

import fcntl
import os
import struct

from errors import GuardError

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


def open_capture(device, width, height):
    """Opens a device path as an OpenCV capture asking for MJPG at the given size."""
    import cv2

    capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not capture.isOpened():
        capture.release()
        raise GuardError("camera", f"Can't open camera {device}", retryable=True)
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture


### --- OTHER APPS USING THE CAMERA --- ###
IN_OPEN = 0x20
IN_CLOSE = 0x08 | 0x10  # IN_CLOSE_WRITE | IN_CLOSE_NOWRITE
IN_NONBLOCK = 0o4000
IN_CLOEXEC = 0o2000000
EVENT_HEADER = struct.Struct("iIII")  # struct inotify_event without its name


class CameraUsers:
    """Notices other processes opening a camera, and lists those holding it open.

    Linux can't say which app wants a camera, but inotify reports every open of its
    device file, and /proc shows which processes hold it. Facelock's own opens are
    discarded with forget_own_opens().
    """

    def __init__(self, device_path):
        import ctypes

        self.path = os.path.realpath(device_path)
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._fd = self._libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if self._fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        if self._libc.inotify_add_watch(self._fd, self.path.encode(), IN_OPEN | IN_CLOSE) < 0:
            error = ctypes.get_errno()
            os.close(self._fd)
            raise OSError(error, f"can't watch {self.path}")

    def _read_masks(self):
        masks = []
        while True:
            try:
                data = os.read(self._fd, 4096)
            except BlockingIOError:
                return masks
            offset = 0
            while offset + EVENT_HEADER.size <= len(data):
                _wd, mask, _cookie, name_length = EVENT_HEADER.unpack_from(data, offset)
                masks.append(mask)
                offset += EVENT_HEADER.size + name_length

    def opened_since_last_check(self):
        """Whether anything opened the camera since the last check or forget_own_opens()."""
        return any(mask & IN_OPEN for mask in self._read_masks())

    def forget_own_opens(self):
        self._read_masks()

    def holders(self):
        """Names of the other processes holding the camera open, as far as /proc lets us see."""
        own = os.getpid()
        names = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit() or int(pid) == own:
                continue
            try:
                fds = os.listdir(f"/proc/{pid}/fd")
            except OSError:
                continue  # gone, or another user's process
            for fd in fds:
                try:
                    if os.readlink(f"/proc/{pid}/fd/{fd}") == self.path:
                        with open(f"/proc/{pid}/comm") as comm:
                            names.append(comm.read().strip())
                        break
                except OSError:
                    continue
        return names

    def wait_for_change(self, timeout):
        """Returns when the camera is opened or closed, or after timeout seconds."""
        import select

        select.select([self._fd], [], [], timeout)
        self._read_masks()

    def close(self):
        os.close(self._fd)
