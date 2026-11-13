"""Tests for the macOS app's logic that needs no screen, camera or models.

Run with: python -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "macos"))

from gaze import camera_to_screen, pupil_offset

WIDTH, HEIGHT, RANGE = 1920, 1080, 100
EYES = [(240, 270), (1680, 270), (240, 810), (1680, 810)]


def offsets(x, y):
    return [pupil_offset(eye, camera_to_screen(x, y, WIDTH, HEIGHT), RANGE, RANGE, WIDTH) for eye in EYES]


class GazeTests(unittest.TestCase):
    def test_someone_on_the_left_of_the_camera_image_makes_every_eye_look_right(self):
        self.assertTrue(all(dx > 0 for dx, _ in offsets(0, 0.5)))

    def test_someone_on_the_right_makes_every_eye_look_left(self):
        self.assertTrue(all(dx < 0 for dx, _ in offsets(1, 0.5)))

    def test_someone_at_the_top_makes_every_eye_look_up(self):
        self.assertTrue(all(dy < 0 for _, dy in offsets(0.5, 0)))

    def test_eyes_converge_on_someone_in_the_middle(self):
        left, right = offsets(0.5, 0.5)[:2]
        self.assertTrue(left[0] > 0 and right[0] < 0)

    def test_pupils_stay_in_range(self):
        for x in (0, 0.5, 1):
            for y in (0, 0.5, 1):
                for dx, dy in offsets(x, y):
                    self.assertLessEqual(abs(dx), RANGE)
                    self.assertLessEqual(abs(dy), RANGE)


try:
    from settings import DEFAULTS, Settings
except ImportError:
    Settings = None


@unittest.skipIf(Settings is None, "no settings module")
class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "settings.json")

    def test_defaults_without_a_file(self):
        self.assertEqual(Settings(self.path).get("model"), DEFAULTS["model"])

    def test_values_persist(self):
        Settings(self.path).set("interval-ms", 2000)
        self.assertEqual(Settings(self.path).get("interval-ms"), 2000)

    def test_listeners_hear_only_real_changes(self):
        settings, heard = Settings(self.path), []
        settings.on_change(heard.append)
        settings.set("model", "buffalo_sc")
        settings.set("model", "buffalo_sc")
        self.assertEqual(heard, ["model"])

    def test_wrong_types_and_unknown_keys_are_ignored(self):
        with open(self.path, "w") as handle:
            json.dump({"interval-ms": "fast", "absence-grace-s": 20, "bogus": 1}, handle)
        settings = Settings(self.path)
        self.assertEqual(settings.get("interval-ms"), DEFAULTS["interval-ms"])
        self.assertEqual(settings.get("absence-grace-s"), 20)

    def test_a_corrupt_file_falls_back_to_defaults(self):
        with open(self.path, "w") as handle:
            handle.write("{nope")
        self.assertEqual(Settings(self.path).get("enabled"), DEFAULTS["enabled"])


if __name__ == "__main__":
    unittest.main()
