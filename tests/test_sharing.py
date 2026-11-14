"""Tests for handing the camera to other apps. No camera needed.

Run with: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "extension", "daemon"))
sys.path.insert(0, os.path.dirname(__file__))  # for test_daemon's fakes

from policy import Policy
from sharing import RESUME_AFTER_ATTEMPT_S, RESUME_AFTER_USE_S, CameraSharing


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeUsers:
    """Another app's use of the camera, as a schedule: (from, until) seconds it's held."""

    def __init__(self, clock, opened=False, held=()):
        self.clock, self.opened, self.held = clock, opened, held
        self.own_opens_forgotten = 0

    def opened_since_last_check(self):
        opened, self.opened = self.opened, False
        return opened

    def forget_own_opens(self):
        self.own_opens_forgotten += 1

    def holders(self):
        return ["zoom"] if any(start <= self.clock.now < end for start, end in self.held) else []

    def wait_for_change(self, timeout):
        self.clock.now += timeout


class FakeCamera:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class CameraSharingTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.events = []
        self.opened = []

    def sharing(self, users):
        def open_camera():
            camera = FakeCamera()
            self.opened.append(self.clock.now)
            return camera

        return CameraSharing(users, open_camera, lambda event, **fields: self.events.append((event, fields)),
                             clock=self.clock)

    def test_nothing_happens_without_another_app(self):
        camera = FakeCamera()
        self.assertIs(self.sharing(FakeUsers(self.clock)).check(camera), camera)
        self.assertFalse(camera.closed)
        self.assertEqual(self.events, [])

    def test_lets_go_while_another_app_uses_it_then_takes_it_back(self):
        users = FakeUsers(self.clock, opened=True, held=[(0, 30)])
        camera = FakeCamera()
        reopened = self.sharing(users).check(camera)
        self.assertTrue(camera.closed)
        self.assertIsNot(reopened, camera)
        self.assertEqual(self.events, [("paused", {"apps": ["zoom"]}), ("resumed", {})])
        self.assertGreaterEqual(self.opened[0], 30 + RESUME_AFTER_USE_S)
        self.assertLess(self.opened[0], 30 + RESUME_AFTER_USE_S + 2)

    def test_waits_longer_after_an_attempt_that_never_held_it(self):
        users = FakeUsers(self.clock, opened=True)
        self.sharing(users).check(FakeCamera())
        self.assertEqual(self.events[0], ("paused", {"apps": []}))
        self.assertGreaterEqual(self.opened[0], RESUME_AFTER_ATTEMPT_S)

    def test_a_retry_during_the_wait_is_let_through(self):
        # The first attempt failed at once; the user clicked again 8 s later.
        users = FakeUsers(self.clock, opened=True, held=[(8, 20)])
        self.sharing(users).check(FakeCamera())
        self.assertGreaterEqual(self.opened[0], 20 + RESUME_AFTER_USE_S)

    def test_its_own_reopening_is_not_taken_for_another_app(self):
        users = FakeUsers(self.clock, opened=True, held=[(0, 5)])
        sharing = self.sharing(users)
        sharing.check(FakeCamera())
        self.assertEqual(users.own_opens_forgotten, 1)


class PolicyResetTests(unittest.TestCase):
    def test_absence_starts_over_after_reset(self):
        policy = Policy(5, 1)
        policy.observe(0, False, 0)
        policy.reset()
        # Without the reset, 100 s of absence would lock at once.
        self.assertEqual(policy.observe(100, False, 0), [])
        self.assertEqual(policy.observe(105, False, 0), ["absent"])


class MonitorPauseTests(unittest.TestCase):
    def test_no_lock_right_after_a_call_had_the_camera(self):
        import numpy as np

        from camera import WARMUP_S
        from monitor import WatchSettings, monitor
        from test_daemon import FakeBackend, FakeCamera as DaemonCamera, FakeClock as DaemonClock, StopLoop, face

        owner = np.array([1.0, 0.0])
        clock = DaemonClock()
        scene = lambda t: [face(owner)] if t < 10 else []  # nobody there after the call

        class CallAtTen:
            """A call takes the camera at 10 s for two minutes."""
            done = False

            def check(self, camera):
                if self.done or clock.now < 10:
                    return camera
                self.done = True
                clock.now += 120
                return DaemonCamera(clock, scene, end=200)

        events = []
        with self.assertRaises(StopLoop):
            monitor(DaemonCamera(clock, scene, end=200), FakeBackend(), owner, Policy(5, 1),
                    lambda event, **fields: events.append((clock.now, event, fields)),
                    WatchSettings(1000, 0.4, 40), clock=clock, sleep=clock.sleep, sharing=CallAtTen())
        locks = [t for t, event, fields in events if event == "trigger" and fields["kind"] == "absent"]
        self.assertEqual(len(locks), 1)
        self.assertGreaterEqual(locks[0], 130 + WARMUP_S + 5)


@unittest.skipUnless(sys.platform.startswith("linux"), "inotify and /proc are Linux only")
class CameraUsersTests(unittest.TestCase):
    """The real detection, on a file: inotify and /proc treat it like a camera device."""

    def setUp(self):
        from camera_v4l2 import CameraUsers

        handle, self.path = tempfile.mkstemp()
        os.close(handle)
        self.users = CameraUsers(self.path)
        self.users.forget_own_opens()

    def tearDown(self):
        self.users.close()
        os.remove(self.path)

    def hold(self):
        process = subprocess.Popen(
            [sys.executable, "-c", f"import sys, time; f = open({self.path!r}); print('open', flush=True); time.sleep(30)"],
            stdout=subprocess.PIPE, text=True)
        process.stdout.readline()
        return process

    def test_sees_another_process_open_and_hold_it(self):
        process = self.hold()
        try:
            self.assertTrue(self.users.opened_since_last_check())
            self.assertFalse(self.users.opened_since_last_check())  # each open counts once
            self.assertEqual(len(self.users.holders()), 1)
        finally:
            process.kill()
            process.wait()
        deadline = time.monotonic() + 5
        while self.users.holders() and time.monotonic() < deadline:
            self.users.wait_for_change(0.2)
        self.assertEqual(self.users.holders(), [])

    def test_its_own_opens_can_be_forgotten(self):
        with open(self.path):
            pass
        self.users.forget_own_opens()
        self.assertFalse(self.users.opened_since_last_check())

    def test_its_own_process_is_not_a_holder(self):
        with open(self.path):
            self.assertEqual(self.users.holders(), [])


if __name__ == "__main__":
    unittest.main()
