#!/usr/bin/env python3
"""Camera and face-recognition worker for the Facelock GNOME extension.

Talks to its parent over JSON lines on stdout and exits when stdin closes, so it
can't outlive the shell and leave the camera on. Modes:

  (default)        watch the camera and report status and triggers; "track" on
                   stdin snaps at the camera's framerate until "untrack"
  --list-cameras   print the available cameras
  --list-models    print the face models and whether a usable GPU is present
  --enroll SRC     validate an image and store it as the reference face
  --capture        stream preview frames until "snap" arrives on stdin
  --prepare        download the models if needed and warm them up
  --unlock         check once whether the face in view may unlock the screen, and with
                   --phone, ask the paired phone to approve; reports "unlock"
  --pair           show a code for the phone page, and save the phone that pairs with it
"""

import os

# Without these, NumPy and OpenCV each start a thread per core, which this
# daemon never uses. They must be set before either is imported.
for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_variable, "1")

import argparse
import logging
import sys
import threading

from backends import CPU, DEFAULT_MODEL, GPU, MODELS, gpu_name, describe_models, load_backend
from camera import list_cameras, open_camera, resolve_device, watch_camera_users
from capture import capture
from enrollment import enroll
from errors import EXIT_FATAL, EXIT_RETRYABLE, GuardError
from monitor import WatchSettings, monitor
from paths import APP_DIR, data_home
from phone import PAGE_URL
from policy import Policy
from protocol import open_protocol_stream, watch_stdin
from recognition import load_reference
from relay import DEFAULT_SERVER
from sharing import CameraSharing
from unlock import UnlockSettings, check_face

log = logging.getLogger("facelock")


def load(args, emit):
    """Loads the chosen model on the chosen hardware, using the CPU if there's no GPU."""
    compute = args.compute
    if compute == GPU and gpu_name() is None:
        log.warning("No usable GPU found, so using the CPU")
        compute = CPU
    return load_backend(MODELS[args.model], args.detection_threshold, compute, emit)


def run_monitor(args, emit):
    tracking = threading.Event()
    commands = {"track": tracking.set, "untrack": tracking.clear}
    watch_stdin(lambda line: commands.get(line, lambda: None)())
    if not os.path.exists(args.reference):
        raise GuardError("no_reference", "No reference image has been set", retryable=False)
    backend = load(args, emit)
    reference = load_reference(backend, args.reference)
    sharing = None
    if args.share_camera:
        # Reopens the same camera, even if "auto" would pick another one by then.
        device = resolve_device(args.device)
        users = watch_camera_users(device)
        if users is not None:
            sharing = CameraSharing(users, lambda: open_camera(device), emit)
    camera = sharing.open_first() if sharing else open_camera(args.device)
    emit("ready", model=args.model, compute=backend.compute, requested=args.compute)
    settings = WatchSettings(args.interval_ms, match_threshold(args), args.min_face_px)
    policy = Policy(args.absence_grace, args.intruder_grace)
    monitor(camera, backend, reference, policy, emit, settings, tracking=tracking, sharing=sharing)


def run_unlock(args, emit):
    import phone

    watch_stdin()
    paired = None
    if args.phone:
        paired = phone.load_phone()
        if paired is None:
            emit("unlock", ok=False, reason="No phone is paired")
            return
    if not os.path.exists(args.reference):
        raise GuardError("no_reference", "No reference image has been set", retryable=False)
    backend = load(args, emit)
    reference = load_reference(backend, args.reference)
    camera = open_camera(args.device)
    try:
        reason = check_face(camera, backend, reference,
                            UnlockSettings(match_threshold(args), args.min_face_px, args.liveness), emit)
    finally:
        camera.close()
    if reason is None and paired is not None:
        reason = phone.approve(paired, args.number_match, emit)
    emit("unlock", ok=reason is None, reason=reason)


def run_pair(args, emit):
    import phone

    watch_stdin()
    phone.pair(args.relay, args.page_url, emit)


def run_enroll(args, emit):
    enroll(load(args, emit), args.enroll, args.reference, emit)


def run_prepare(args, emit):
    backend = load(args, emit)
    backend.warm_up()
    emit("prepared", model=args.model, compute=backend.compute)


def match_threshold(args):
    """The user's threshold for this model, or the model's own default."""
    if args.match_threshold is not None:
        return args.match_threshold
    return MODELS[args.model].default_match_threshold


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-cameras", action="store_true")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--enroll", metavar="SRC")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--unlock", action="store_true")
    parser.add_argument("--liveness", action="store_true", help="with --unlock, ask for a head turn")
    parser.add_argument("--phone", action="store_true", help="with --unlock, ask the paired phone too")
    parser.add_argument("--number-match", action="store_true",
                        help="with --phone, pick the number on the screen on the phone")
    parser.add_argument("--pair", action="store_true")
    parser.add_argument("--relay", default=DEFAULT_SERVER, help="the ntfy server, for --pair")
    parser.add_argument("--page-url", default=PAGE_URL,
                        help="where the phone page is published, for --pair")
    parser.add_argument("--reference", default=os.path.join(data_home(), APP_DIR, "reference.jpg"))
    parser.add_argument("--device", default="auto", help="camera, or auto for the first physical one")
    parser.add_argument("--model", choices=sorted(MODELS), default=DEFAULT_MODEL)
    parser.add_argument("--compute", choices=(CPU, GPU), default=CPU)
    parser.add_argument("--share-camera", action="store_true",
                        help="let go of the camera while another app uses it (Linux)")
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--match-threshold", type=float, default=None,
                        help="the model's own default if not given")
    parser.add_argument("--detection-threshold", type=float, default=0.5)
    parser.add_argument("--min-face-px", type=int, default=40)
    parser.add_argument("--absence-grace", type=float, default=10.0)
    parser.add_argument("--intruder-grace", type=float, default=1.0)
    return parser.parse_args(argv)


def main():
    logging.basicConfig(level=logging.INFO, format="facelock: %(message)s")
    args = parse_args()
    emit = open_protocol_stream()
    try:
        if args.list_cameras:
            emit("cameras", cameras=list_cameras())
        elif args.list_models:
            emit("models", **describe_models())
        elif args.enroll:
            run_enroll(args, emit)
        elif args.capture:
            capture(args.device, emit)
        elif args.prepare:
            run_prepare(args, emit)
        elif args.unlock:
            run_unlock(args, emit)
        elif args.pair:
            run_pair(args, emit)
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
