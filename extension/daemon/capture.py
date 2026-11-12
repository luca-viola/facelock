"""Streaming camera previews to Settings until the user snaps a reference photo."""

import os
import threading
import time

from camera import WARMUP_S, open_camera
from files import private_dir, write_private
from protocol import watch_stdin

PREVIEW_PERIOD_S = 0.1


def capture(device, emit):
    import cv2

    snap = threading.Event()
    closed = threading.Event()
    # Leaves the loop rather than exiting, so the preview of the user's face is removed.
    watch_stdin(lambda line: snap.set() if line == "snap" else None, closed.set)

    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.cache")
    directory = private_dir(os.path.join(base, "faceguard"))
    preview_path = os.path.join(directory, "preview.jpg")
    capture_path = os.path.join(directory, "capture.jpg")

    camera = open_camera(device)
    time.sleep(WARMUP_S)
    emit("ready")
    try:
        while not closed.is_set():
            frame = camera.read()
            quality = 95 if snap.is_set() else 70
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                continue
            if snap.is_set():
                write_private(capture_path, encoded.tobytes())
                emit("captured", path=capture_path)
                return
            write_private(preview_path, encoded.tobytes())
            emit("frame", path=preview_path)
            time.sleep(PREVIEW_PERIOD_S)
    finally:
        camera.close()
        if os.path.exists(preview_path):
            os.remove(preview_path)
