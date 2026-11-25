"""The watch loop: snap, recognize, and report status and triggers."""

import collections
import time
from dataclasses import dataclass

from camera import WARMUP_S
from policy import Policy
from recognition import classify_faces

STATUS_PERIOD_S = 1.0


@dataclass(frozen=True)
class WatchSettings:
    interval_ms: int
    match_threshold: float
    min_face_px: int


def monitor(camera, backend, reference, policy, emit, settings, clock=time.monotonic, sleep=time.sleep,
            tracking=None, sharing=None):
    """Runs the watch loop until the camera fails (raises) or forever.

    While the tracking event is set, it snaps as fast as the camera delivers frames,
    so something following the other face can keep up. With sharing, it lets another
    app have the camera and nothing is watched meanwhile.
    """
    interval_s = settings.interval_ms / 1000
    warmup_until = clock() + WARMUP_S
    last_status = None
    last_status_at = 0.0
    processed = collections.deque(maxlen=20)

    while True:
        if sharing is not None:
            shared = sharing.check(camera)
            if shared is not camera:
                # Nothing was seen during the pause, so it all starts over.
                camera = shared
                policy.reset()
                warmup_until = clock() + WARMUP_S
                last_status = None
        started = clock()
        frame = camera.read()
        if started < warmup_until:
            sleep(0.05)
            continue

        owner, other_faces, score = classify_faces(
            backend.faces(frame), reference, backend.similarity,
            settings.match_threshold, settings.min_face_px)
        others = len(other_faces)

        # Sent before any trigger, so an action can use it straight away. Without a
        # match, the "other" face may be the owner's own at a bad angle.
        if owner and other_faces:
            height, width = frame.shape[:2]
            x, y = max(other_faces, key=lambda face: face.size).center(width, height)
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
            (sleep if sharing is None else sharing.wait)(remaining)
