"""A simple liveness check: the head has to turn to one side and back.

How far the nose sits from the middle of the eyes, measured in eye spacings, changes when a
real head turns, because the nose sticks out. On a flat photo it can't: turning or tilting the
photo squeezes the nose offset and the eye spacing alike. A video of you turning still passes,
so this stops a printed or on-screen photo, not a determined attacker.

Pure logic with no camera or model access, so it can be tested directly.
"""

FRONTAL = 0.12  # at most this far off-centre counts as looking straight at the camera
TURNED = 0.30  # at least this far counts as a turn


def nose_offset(landmarks):
    """How far the nose is from the middle of the eyes, in eye spacings. Its size is the turn."""
    (lx, ly), (rx, ry), (nx, _ny) = landmarks
    spacing = ((rx - lx) ** 2 + (ry - ly) ** 2) ** 0.5
    if spacing < 1e-6:
        return 0.0
    return (nx - (lx + rx) / 2) / spacing


class HeadTurn:
    """Passes once the face has looked straight ahead, turned to either side, and looked back.

    Feed it one face per frame. Frames without landmarks are skipped.
    """

    def __init__(self, frontal=FRONTAL, turned=TURNED):
        self.frontal = frontal
        self.turned = turned
        self.stage = "ahead"  # then "turn", "back", and "done"

    @property
    def passed(self):
        return self.stage == "done"

    def observe(self, landmarks):
        if landmarks is None or self.passed:
            return self.passed
        offset = abs(nose_offset(landmarks))
        if self.stage == "ahead" and offset <= self.frontal:
            self.stage = "turn"
        elif self.stage == "turn" and offset >= self.turned:
            self.stage = "back"
        elif self.stage == "back" and offset <= self.frontal:
            self.stage = "done"
        return self.passed
