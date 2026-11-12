#!/usr/bin/env python3
"""Camera and face-recognition worker for the Face Guard GNOME extension.

Talks to its parent over JSON lines on stdout and exits when stdin closes, so it
can't outlive the shell and leave the camera on. Modes:

  (default)        watch the camera and report status and triggers; "track" on
                   stdin snaps at the camera's framerate until "untrack"
  --list-cameras   print the available cameras
  --enroll SRC     validate an image and store it as the reference face
  --capture        stream preview frames until "snap" arrives on stdin
  --prepare        download the models if needed and warm them up
"""

import argparse
import logging
import os
import sys
import threading

from backends import CPU, MODELS, load_backend
from camera import list_cameras, open_camera
from capture import capture
from enrollment import enroll
from errors import EXIT_FATAL, EXIT_RETRYABLE, GuardError
from monitor import WatchSettings, monitor
from policy import Policy
from protocol import open_protocol_stream, watch_stdin
from recognition import load_reference

log = logging.getLogger("faceguard")

# The extension still identifies the CPU by onnxruntime's provider name.
PROVIDER_NAMES = {CPU: "CPUExecutionProvider"}


def run_monitor(args, emit):
    tracking = threading.Event()
    commands = {"track": tracking.set, "untrack": tracking.clear}
    watch_stdin(lambda line: commands.get(line, lambda: None)())
    if not os.path.exists(args.reference):
        raise GuardError("no_reference", "No reference image has been set", retryable=False)
    backend = load_backend(MODELS["buffalo_l"], args.detection_threshold, emit)
    reference = load_reference(backend, args.reference)
    camera = open_camera(args.device)
    emit("ready", provider=PROVIDER_NAMES.get(backend.compute, "CUDAExecutionProvider"))
    settings = WatchSettings(args.interval_ms, args.match_threshold, args.min_face_px)
    policy = Policy(args.absence_grace, args.intruder_grace)
    monitor(camera, backend, reference, policy, emit, settings, tracking=tracking)


def run_enroll(args, emit):
    backend = load_backend(MODELS["buffalo_l"], args.detection_threshold, emit)
    enroll(backend, args.enroll, args.reference, emit)


def run_prepare(args, emit):
    backend = load_backend(MODELS["buffalo_l"], args.detection_threshold, emit)
    backend.warm_up()
    emit("prepared", provider=PROVIDER_NAMES.get(backend.compute, "CUDAExecutionProvider"))


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
            capture(args.device, emit)
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
