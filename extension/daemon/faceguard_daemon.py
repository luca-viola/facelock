#!/usr/bin/env python3
"""Camera and face-recognition worker for the Face Guard GNOME extension.

Talks to its parent over JSON lines on stdout and exits when stdin closes, so it
can't outlive the shell and leave the camera on. Modes:

  (default)        watch the camera and report status and triggers; "track" on
                   stdin snaps at the camera's framerate until "untrack"
  --list-cameras   print the available cameras
  --enroll SRC     validate an image and store it as the reference face
  --capture        stream preview frames until "snap" arrives on stdin
  --prepare        download the models if needed and warm up the GPU cache
"""

import argparse
import collections
import fcntl
import json
import logging
import os
import struct
import sys
import threading
import time

from policy import Policy

# Requested size; the camera driver may pick the nearest one it supports.
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
# The first frames after opening are often dark while auto-exposure settles, and
# must not count as "owner absent".
WARMUP_S = 1.5
FRAME_TIMEOUT_S = 5.0
STATUS_PERIOD_S = 1.0
PREVIEW_PERIOD_S = 0.1
CAMERA_OPEN_ATTEMPTS = 10
CAMERA_RETRY_S = 0.5

# Exit codes the extension acts on.
EXIT_RETRYABLE = 3  # camera or model trouble that may clear up by itself
EXIT_FATAL = 4  # needs the user to change something, so don't restart

VIDIOC_QUERYCAP = 0x80685600
V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_DEVICE_CAPS = 0x80000000
V4L2_LOOPBACK_DRIVER = "v4l2 loopback"
BY_ID_DIR = "/dev/v4l/by-id"
MODEL_DIR = os.path.expanduser("~/.insightface/models/buffalo_l")

log = logging.getLogger("faceguard")


class GuardError(Exception):
    def __init__(self, code, message, retryable):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


### --- PROTOCOL --- ###
def open_protocol_stream():
    """Claims the real stdout for JSON and points fd 1 at stderr.

    insightface prints progress to stdout, which would corrupt the protocol.
    """
    stream = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)

    def emit(event, **fields):
        stream.write(json.dumps({"event": event, **fields}) + "\n")

    return emit


### --- CAMERAS --- ###
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


### --- FACE ANALYSIS --- ###
class Analyzer:
    def __init__(self, detection_threshold):
        import onnxruntime
        from insightface.app import FaceAnalysis

        available = onnxruntime.get_available_providers()
        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in available]
        # Landmarks and gender/age would run on every face for nothing.
        self._app = FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection", "recognition"],
            providers=providers,
        )
        self._app.prepare(ctx_id=0, det_thresh=detection_threshold, det_size=(640, 640))
        self.provider = self._app.models["recognition"].session.get_providers()[0]

    def faces(self, image):
        return self._app.get(image)

    def warm_up(self):
        """Runs both models once, because the first GPU inference can be very slow."""
        import numpy as np

        self._app.get(np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), np.uint8))
        self._app.models["recognition"].get_feat(np.zeros((112, 112, 3), np.uint8))


def models_present(directory=MODEL_DIR):
    try:
        return any(name.endswith(".onnx") for name in os.listdir(directory))
    except OSError:
        return False


def load_analyzer(detection_threshold, emit, analyzer_class=Analyzer):
    """Loads buffalo_l, saying what's happening since it can take minutes the first time."""
    present = models_present()
    if present:
        emit("loading", detail="Loading face models. The first run can take a minute.")
    else:
        emit("loading", detail="Downloading the buffalo_l face models, a few hundred MB.")
    try:
        return analyzer_class(detection_threshold)
    except Exception as error:
        log.exception("Couldn't load buffalo_l")
        message = (f"Couldn't load buffalo_l: {error}" if present
                   else "Couldn't download the buffalo_l face models. Check your connection.")
        raise GuardError("model", message, retryable=True) from error


def face_size(face):
    x1, y1, x2, y2 = face.bbox
    return min(x2 - x1, y2 - y1)


def classify_faces(faces, reference, match_threshold, min_face_px):
    """Returns (owner present, the other faces, best match score or None).

    Only the best match can be the owner, so a second face scoring above the
    threshold still counts as another person.
    """
    candidates = [face for face in faces if face_size(face) >= min_face_px]
    if not candidates:
        return False, [], None
    scores = [float(face.normed_embedding.dot(reference)) for face in candidates]
    best = max(scores)
    if best >= match_threshold:
        owner = scores.index(best)
        return True, candidates[:owner] + candidates[owner + 1:], best
    return False, candidates, best


def face_center(face, frame):
    """Returns where a face is in the frame, from 0 to 1 on each axis."""
    x1, y1, x2, y2 = face.bbox
    height, width = frame.shape[:2]
    return float((x1 + x2) / 2 / width), float((y1 + y2) / 2 / height)


def load_reference(analyzer, path):
    import cv2

    image = cv2.imread(path)
    if image is None:
        raise GuardError("no_reference", f"Can't read the reference image {path}", retryable=False)
    faces = analyzer.faces(image)
    if len(faces) != 1:
        raise GuardError(
            "bad_reference",
            f"The reference image must show exactly one face, found {len(faces)}",
            retryable=False,
        )
    return faces[0].normed_embedding


### --- MONITOR MODE --- ###
def monitor(camera, analyzer, reference, policy, emit, config, clock=time.monotonic, sleep=time.sleep,
            tracking=None):
    """Runs the watch loop until the camera fails (raises) or forever.

    While the tracking event is set, it snaps as fast as the camera delivers frames,
    so something following the other face can keep up.
    """
    interval_s = config["interval_ms"] / 1000
    warmup_until = clock() + WARMUP_S
    last_status = None
    last_status_at = 0.0
    processed = collections.deque(maxlen=20)

    while True:
        started = clock()
        frame = camera.read()
        if started < warmup_until:
            sleep(0.05)
            continue

        faces = analyzer.faces(frame)
        owner, other_faces, score = classify_faces(
            faces, reference, config["match_threshold"], config["min_face_px"])
        others = len(other_faces)

        # Sent before any trigger, so an action can use it straight away. Without a
        # match, the "other" face may be the owner's own at a bad angle.
        if owner and other_faces:
            x, y = face_center(max(other_faces, key=face_size), frame)
            emit("intruder_at", x=round(x, 3), y=round(y, 3))

        now = clock()
        processed.append(now)
        for kind in policy.observe(now, owner, others):
            emit("trigger", kind=kind, others=others)

        state = Policy.state(owner, others)
        if state != last_status or now - last_status_at >= STATUS_PERIOD_S:
            rate = (len(processed) - 1) / (processed[-1] - processed[0]) if len(processed) > 1 else 0.0
            emit("status", state=state, others=others,
                 score=None if score is None else round(score, 3),
                 camera_fps=round(camera.measured_fps(), 1),
                 snap_rate=round(rate, 2))
            last_status = state
            last_status_at = now

        if tracking is not None and tracking.is_set():
            continue
        remaining = interval_s - (clock() - started)
        if remaining > 0:
            sleep(remaining)


def watch_stdin(on_line=None, on_close=lambda: os._exit(0)):
    """Calls on_close at stdin EOF, which is how a dead parent shows up."""
    def watch():
        for line in sys.stdin:
            if on_line:
                on_line(line.strip())
        on_close()

    threading.Thread(target=watch, daemon=True).start()


def run_monitor(args, emit):
    tracking = threading.Event()
    commands = {"track": tracking.set, "untrack": tracking.clear}
    watch_stdin(lambda line: commands.get(line, lambda: None)())
    if not os.path.exists(args.reference):
        raise GuardError("no_reference", "No reference image has been set", retryable=False)
    analyzer = load_analyzer(args.detection_threshold, emit)
    reference = load_reference(analyzer, args.reference)
    camera = open_camera(args.device)
    emit("ready", provider=analyzer.provider)
    config = {
        "interval_ms": args.interval_ms,
        "match_threshold": args.match_threshold,
        "min_face_px": args.min_face_px,
    }
    monitor(camera, analyzer, reference, Policy(args.absence_grace, args.intruder_grace), emit, config,
            tracking=tracking)


### --- ENROLLMENT --- ###
def private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def write_private(path, data):
    """Writes a file readable only by the user, replacing any old one atomically."""
    temporary = f"{path}.{os.getpid()}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.replace(temporary, path)


def run_enroll(args, emit):
    import cv2

    image = cv2.imread(args.enroll)
    if image is None:
        raise GuardError("bad_reference", f"Can't read {args.enroll} as an image", retryable=False)
    faces = load_analyzer(args.detection_threshold, emit).faces(image)
    if not faces:
        raise GuardError("bad_reference", "No face found in that image", retryable=False)
    if len(faces) > 1:
        raise GuardError("bad_reference",
                         f"Found {len(faces)} faces. Use an image with only yours.", retryable=False)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise GuardError("bad_reference", "Couldn't encode that image", retryable=False)
    private_dir(os.path.dirname(args.reference))
    write_private(args.reference, encoded.tobytes())
    emit("enrolled", path=args.reference, detection_score=round(float(faces[0].det_score), 3))


### --- PREPARE MODE --- ###
def run_prepare(args, emit):
    analyzer = load_analyzer(args.detection_threshold, emit)
    analyzer.warm_up()
    emit("prepared", provider=analyzer.provider)


### --- CAPTURE MODE --- ###
def run_capture(args, emit):
    import cv2

    snap = threading.Event()
    closed = threading.Event()
    # Leaves the loop rather than exiting, so the preview of the user's face is removed.
    watch_stdin(lambda line: snap.set() if line == "snap" else None, closed.set)

    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.cache")
    directory = private_dir(os.path.join(base, "faceguard"))
    preview_path = os.path.join(directory, "preview.jpg")
    capture_path = os.path.join(directory, "capture.jpg")

    camera = open_camera(args.device)
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


### --- ENTRY POINT --- ###
def parse_args(argv=None):
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-cameras", action="store_true")
    parser.add_argument("--enroll", metavar="SRC")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--reference", default=os.path.join(data_home, "faceguard", "reference.jpg"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--match-threshold", type=float, default=0.4)
    parser.add_argument("--detection-threshold", type=float, default=0.5)
    parser.add_argument("--min-face-px", type=int, default=40)
    parser.add_argument("--absence-grace", type=float, default=10.0)
    parser.add_argument("--intruder-grace", type=float, default=1.0)
    return parser.parse_args(argv)


def main():
    logging.basicConfig(level=logging.INFO, format="faceguard: %(message)s")
    args = parse_args()
    emit = open_protocol_stream()
    try:
        if args.list_cameras:
            emit("cameras", cameras=list_cameras())
        elif args.enroll:
            run_enroll(args, emit)
        elif args.capture:
            run_capture(args, emit)
        elif args.prepare:
            run_prepare(args, emit)
        else:
            run_monitor(args, emit)
    except GuardError as error:
        emit("error", code=error.code, message=str(error), retryable=error.retryable)
        # A camera thread stuck in the driver must not keep the process alive.
        logging.shutdown()
        sys.stderr.flush()
        os._exit(EXIT_RETRYABLE if error.retryable else EXIT_FATAL)
    except Exception as error:
        log.exception("Unexpected failure")
        emit("error", code="internal", message=str(error), retryable=True)
        os._exit(EXIT_RETRYABLE)
    # Skips interpreter shutdown, which can hang on a thread stuck in the driver.
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
