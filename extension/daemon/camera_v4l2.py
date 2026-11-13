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
