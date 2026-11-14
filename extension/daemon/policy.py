"""Decides when a stream of face observations should trigger an action.

Pure logic with no camera, model or clock access, so it can be tested directly.
"""

OWNER = "owner"
ABSENT = "absent"
INTRUDER = "intruder"

# How long the extra faces must stay gone before an intruder episode ends.
INTRUDER_CLEAR_S = 2.0


class Policy:
    """Turns per-frame observations into at most one trigger per episode.

    A face that doesn't match the owner only counts as an intruder while the
    owner is also matched in the same frame. The owner's own face at a bad angle
    can score below the threshold, and that must read as "owner absent" (which
    has a long grace period) rather than as a stranger.
    """

    def __init__(self, absence_grace_s, intruder_grace_s, clear_s=INTRUDER_CLEAR_S):
        self.absence_grace_s = absence_grace_s
        self.intruder_grace_s = intruder_grace_s
        self.clear_s = clear_s
        self._absent_since = None
        self._absent_fired = False
        self._intruder_since = None
        self._intruder_active = False
        self._clear_since = None

    def reset(self):
        """Starts over, as after a pause in which nothing was seen."""
        self._absent_since = None
        self._absent_fired = False
        self._intruder_since = None
        self._intruder_active = False
        self._clear_since = None

    def observe(self, now, owner_present, other_faces):
        """Records one frame and returns the triggers it caused, oldest first."""
        triggers = []

        if owner_present:
            self._absent_since = None
            self._absent_fired = False
        else:
            if self._absent_since is None:
                self._absent_since = now
            if not self._absent_fired and now - self._absent_since >= self.absence_grace_s:
                self._absent_fired = True
                triggers.append("absent")

        if owner_present and other_faces > 0:
            self._clear_since = None
            if self._intruder_since is None:
                self._intruder_since = now
            if not self._intruder_active and now - self._intruder_since >= self.intruder_grace_s:
                self._intruder_active = True
                triggers.append("intruder")
        else:
            self._intruder_since = None
            if self._intruder_active:
                if other_faces > 0:
                    # Only strangers are matched right now, so nobody has left.
                    self._clear_since = None
                else:
                    if self._clear_since is None:
                        self._clear_since = now
                    if now - self._clear_since >= self.clear_s:
                        self._intruder_active = False
                        self._clear_since = None
                        triggers.append("clear")

        return triggers

    @staticmethod
    def state(owner_present, other_faces):
        if not owner_present:
            return ABSENT
        return INTRUDER if other_faces > 0 else OWNER
