"""Tests for the decision logic and watch loop. No camera, GPU or models needed.

Run with: python -m unittest discover -s tests
"""

import os
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "extension", "daemon"))

import numpy as np

from faceguard_daemon import (
    GuardError, WARMUP_S, classify_faces, face_center, load_analyzer, models_present, monitor)
from policy import Policy

OWNER_VEC = np.array([1.0, 0.0])
STRANGER_VEC = np.array([0.0, 1.0])


def face(vector, size=100, x=0, y=0):
    return SimpleNamespace(normed_embedding=vector, bbox=[x, y, x + size, y + size])


class PolicyTests(unittest.TestCase):
    def run_frames(self, policy, frames):
        return [(t, k) for t, owner, others in frames for k in policy.observe(t, owner, others)]

    def test_owner_alone_never_triggers(self):
        policy = Policy(5, 1)
        self.assertEqual(self.run_frames(policy, [(t, True, 0) for t in range(100)]), [])

    def test_absence_triggers_once_after_grace(self):
        policy = Policy(5, 1)
        frames = [(t, False, 0) for t in range(20)]
        self.assertEqual(self.run_frames(policy, frames), [(5, "absent")])

    def test_owner_returning_resets_absence(self):
        policy = Policy(5, 1)
        frames = [(0, False, 0), (4, False, 0), (4.5, True, 0), (8, False, 0), (12, False, 0)]
        self.assertEqual(self.run_frames(policy, frames), [])

    def test_absence_can_fire_again_in_a_new_episode(self):
        policy = Policy(1, 1)
        frames = [(0, False, 0), (1, False, 0), (2, True, 0), (3, False, 0), (4, False, 0)]
        self.assertEqual(self.run_frames(policy, frames), [(1, "absent"), (4, "absent")])

    def test_stranger_alone_counts_as_absence_not_intruder(self):
        policy = Policy(5, 1)
        frames = [(t, False, 1) for t in range(7)]
        self.assertEqual(self.run_frames(policy, frames), [(5, "absent")])

    def test_intruder_triggers_once_after_grace(self):
        policy = Policy(5, 1)
        frames = [(t, True, 1) for t in range(10)]
        self.assertEqual(self.run_frames(policy, frames), [(1, "intruder")])

    def test_one_frame_flicker_is_ignored(self):
        policy = Policy(5, 1)
        frames = [(0, True, 1), (0.5, True, 0), (1, True, 1), (1.5, True, 0)]
        self.assertEqual(self.run_frames(policy, frames), [])

    def test_zero_grace_fires_on_first_frame(self):
        policy = Policy(5, 0)
        self.assertEqual(self.run_frames(policy, [(0, True, 1)]), [(0, "intruder")])

    def test_intruder_clears_only_after_staying_gone(self):
        policy = Policy(5, 0, clear_s=2)
        frames = [(0, True, 1), (1, True, 0), (2, True, 1), (3, True, 0), (4, True, 0), (5, True, 0)]
        self.assertEqual(self.run_frames(policy, frames), [(0, "intruder"), (5, "clear")])

    def test_intruder_triggers_again_after_leaving_and_returning(self):
        policy = Policy(50, 0, clear_s=2)
        frames = [(t, True, 1) for t in range(5)]
        frames += [(t, True, 0) for t in range(5, 10)]
        frames += [(t, True, 1) for t in range(10, 15)]
        self.assertEqual(self.run_frames(policy, frames), [(0, "intruder"), (7, "clear"), (10, "intruder")])

    def test_owner_looking_away_during_intruder_does_not_clear(self):
        policy = Policy(50, 0, clear_s=1)
        frames = [(0, True, 1), (1, False, 1), (2, False, 1), (3, False, 1), (4, True, 1)]
        self.assertEqual(self.run_frames(policy, frames), [(0, "intruder")])


class ClassifyTests(unittest.TestCase):
    def classify(self, faces):
        owner, others, score = classify_faces(faces, OWNER_VEC, 0.4, 40)
        return owner, len(others), score

    def test_no_faces(self):
        self.assertEqual(self.classify([]), (False, 0, None))

    def test_owner_alone(self):
        self.assertEqual(self.classify([face(OWNER_VEC)]), (True, 0, 1.0))

    def test_stranger_alone(self):
        self.assertEqual(self.classify([face(STRANGER_VEC)]), (False, 1, 0.0))

    def test_owner_and_stranger(self):
        self.assertEqual(self.classify([face(STRANGER_VEC), face(OWNER_VEC)]), (True, 1, 1.0))

    def test_two_faces_above_threshold_still_count_as_another_person(self):
        self.assertEqual(self.classify([face(OWNER_VEC), face(OWNER_VEC)]), (True, 1, 1.0))

    def test_small_faces_are_ignored(self):
        self.assertEqual(self.classify([face(OWNER_VEC), face(STRANGER_VEC, size=20)]), (True, 0, 1.0))

    def test_others_exclude_only_the_owner(self):
        stranger = face(STRANGER_VEC)
        _, others, _ = classify_faces([stranger, face(OWNER_VEC)], OWNER_VEC, 0.4, 40)
        self.assertEqual(others, [stranger])

    def test_face_center_is_relative_to_the_frame(self):
        frame = SimpleNamespace(shape=(720, 1280, 3))
        self.assertEqual(face_center(face(STRANGER_VEC, size=100, x=590, y=310), frame), (0.5, 0.5))


class StopLoop(Exception):
    pass


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeCamera:
    """Delivers one frame per camera_period_s; the scene is chosen by the time."""

    def __init__(self, clock, scene, end, camera_period_s=0.04):
        self.clock, self.scene, self.end, self.period = clock, scene, end, camera_period_s
        self.reads = 0

    def read(self):
        self.clock.now += self.period
        if self.clock.now > self.end:
            raise StopLoop
        self.reads += 1
        return SimpleNamespace(shape=(720, 1280, 3), faces=self.scene(self.clock.now))

    def measured_fps(self):
        return 1 / self.period


class FakeAnalyzer:
    @staticmethod
    def faces(frame):
        return frame.faces


class MonitorTests(unittest.TestCase):
    def run_monitor(self, scene, end, interval_ms=1000, absence=5, intruder=1, tracking=None):
        clock = FakeClock()
        camera = FakeCamera(clock, scene, end)
        events = []
        config = {"interval_ms": interval_ms, "match_threshold": 0.4, "min_face_px": 40}
        with self.assertRaises(StopLoop):
            monitor(camera, FakeAnalyzer(), OWNER_VEC, Policy(absence, intruder),
                    lambda event, **fields: events.append((clock.now, event, fields)),
                    config, clock=clock, sleep=clock.sleep, tracking=tracking)
        return events, camera

    def triggers(self, events):
        return [fields["kind"] for _, event, fields in events if event == "trigger"]

    def test_owner_present_produces_no_triggers(self):
        events, _ = self.run_monitor(lambda t: [face(OWNER_VEC)], 60)
        self.assertEqual(self.triggers(events), [])
        self.assertTrue(any(e == "status" and f["state"] == "owner" for _, e, f in events))

    def test_empty_chair_triggers_absent_after_grace(self):
        events, _ = self.run_monitor(lambda t: [], 60)
        self.assertEqual(self.triggers(events), ["absent"])
        fired_at = next(t for t, e, _ in events if e == "trigger")
        self.assertGreaterEqual(fired_at, WARMUP_S + 5)
        self.assertLess(fired_at, WARMUP_S + 7)

    def test_dark_frames_during_warmup_are_not_absence(self):
        scene = lambda t: [] if t < WARMUP_S else [face(OWNER_VEC)]
        events, _ = self.run_monitor(scene, 30, absence=1)
        self.assertEqual(self.triggers(events), [])

    def test_stranger_joining_then_leaving(self):
        scene = lambda t: ([face(OWNER_VEC), face(STRANGER_VEC)] if 10 <= t < 20 else [face(OWNER_VEC)])
        events, _ = self.run_monitor(scene, 40)
        self.assertEqual(self.triggers(events), ["intruder", "clear"])

    def intruder_positions(self, scene):
        events, _ = self.run_monitor(scene, 10)
        return [(fields["x"], fields["y"]) for _, event, fields in events if event == "intruder_at"]

    def test_position_of_the_largest_other_face_comes_before_the_trigger(self):
        small = face(STRANGER_VEC, size=50, x=0, y=0)
        large = face(STRANGER_VEC, size=200, x=1080, y=520)
        events, _ = self.run_monitor(lambda t: [face(OWNER_VEC), small, large], 10)
        names = [event for _, event, _ in events if event in ("intruder_at", "trigger")]
        self.assertEqual(names[0], "intruder_at")
        self.assertEqual(self.intruder_positions(lambda t: [face(OWNER_VEC), small, large])[0], (0.922, 0.861))

    def test_no_position_without_the_owner_matched(self):
        self.assertEqual(self.intruder_positions(lambda t: [face(STRANGER_VEC)]), [])

    def test_snap_interval_is_respected(self):
        _, camera = self.run_monitor(lambda t: [face(OWNER_VEC)], 100, interval_ms=2000)
        self.assertLess(camera.reads, 100 / 2 + 40)  # plus the warmup-period reads

    def test_tracking_snaps_at_the_camera_framerate(self):
        tracking = threading.Event()
        tracking.set()
        _, camera = self.run_monitor(lambda t: [face(OWNER_VEC)], 10, interval_ms=1000, tracking=tracking)
        # Every frame after the warmup, which reads more slowly, is analyzed.
        self.assertGreaterEqual(camera.reads, (10 - WARMUP_S) / camera.period - 1)

    def test_interval_below_frame_period_is_limited_by_the_camera(self):
        _, camera = self.run_monitor(lambda t: [face(OWNER_VEC)], 10, interval_ms=1)
        self.assertLessEqual(camera.reads, 10 / camera.period)


class LoadAnalyzerTests(unittest.TestCase):
    def load_broken(self):
        def broken(_threshold):
            raise OSError("network down")

        with self.assertLogs("faceguard", "ERROR"), self.assertRaises(GuardError) as caught:
            load_analyzer(0.5, lambda *a, **k: None, analyzer_class=broken)
        return caught.exception

    def test_failure_becomes_a_retryable_model_error(self):
        with mock.patch("faceguard_daemon.models_present", return_value=True):
            error = self.load_broken()
        self.assertEqual(error.code, "model")
        self.assertTrue(error.retryable)
        self.assertIn("network down", str(error))

    def test_failed_download_has_a_short_message(self):
        with mock.patch("faceguard_daemon.models_present", return_value=False):
            error = self.load_broken()
        self.assertEqual(str(error), "Couldn't download the buffalo_l face models. Check your connection.")

    def test_says_what_it_is_doing_before_loading(self):
        events = []
        load_analyzer(0.5, lambda event, **fields: events.append(event), analyzer_class=lambda _: None)
        self.assertEqual(events, ["loading"])

    def test_missing_model_directory_is_not_present(self):
        self.assertFalse(models_present("/nonexistent/faceguard"))


if __name__ == "__main__":
    unittest.main()
