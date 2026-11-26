"""Deciding whether the face in front of the locked screen may unlock it.

Stricter than watching: the match must be closer, over several frames, with nobody else in
view. With liveness on, the head must also turn to one side and back.
"""

import time
from dataclasses import dataclass

from camera import WARMUP_S
from liveness import HeadTurn

UNLOCK_MARGIN = 0.1  # added to the match threshold
REQUIRED_FRAMES = 3  # frames matched at the stricter threshold
FACE_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class UnlockSettings:
    match_threshold: float
    min_face_px: int
    liveness: bool
    timeout_s: float = FACE_TIMEOUT_S

    @property
    def unlock_threshold(self):
        return self.match_threshold + UNLOCK_MARGIN


def check_face(camera, backend, reference, settings, emit, clock=time.monotonic, sleep=time.sleep):
    """Returns None once the owner is recognized, or why not as a short sentence."""
    started = clock()
    while clock() - started < WARMUP_S:
        camera.read()
        sleep(0.05)

    turn = HeadTurn() if settings.liveness else None
    matched = 0
    step = None

    def say(new_step):
        nonlocal step
        if new_step != step:
            step = new_step
            emit("unlock_step", step=step)

    say("look")
    deadline = clock() + settings.timeout_s
    while clock() < deadline:
        frame = camera.read()
        faces = [face for face in backend.faces(frame) if face.size >= settings.min_face_px]
        if not faces:
            continue
        if len(faces) > 1:
            # Someone else could be the one turning their head, so everything starts over.
            matched = 0
            turn = HeadTurn() if settings.liveness else None
            say("alone")
            continue

        face = faces[0]
        score = backend.similarity(face.embedding, reference)
        if score < settings.match_threshold:
            # Not you, so a turn seen so far may not have been yours.
            matched = 0
            turn = HeadTurn() if settings.liveness else None
            say("look")
            continue
        if score >= settings.unlock_threshold:
            matched += 1
        if turn is not None:
            turn.observe(face.landmarks)
            if face.landmarks is None:
                return "The face model doesn't give the points liveness needs"
        if matched >= REQUIRED_FRAMES and score >= settings.unlock_threshold \
                and (turn is None or turn.passed):
            return None
        say("turn" if turn is not None and matched >= 1 and turn.stage in ("turn", "back") else "look")
    return "Your face wasn't recognized" if matched < REQUIRED_FRAMES else "Your head didn't turn"
