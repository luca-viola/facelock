"""Settings kept in a JSON file, with the same keys and defaults as the GNOME schema."""

import json
import os

DATA_DIR = os.path.expanduser("~/Library/Application Support/faceguard")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
REFERENCE_PATH = os.path.join(DATA_DIR, "reference.jpg")

DEFAULTS = {
    "enabled": False,
    "camera-device": "auto",
    "interval-ms": 1000,
    "model": "buffalo_l",
    "use-gpu": False,
    "match-thresholds": {},  # per model; the model's own default if absent
    "detection-threshold": 0.5,
    "min-face-px": 40,
    "absence-grace-s": 10.0,
    "intruder-grace-s": 1.0,
    "intruder-action": "lock",  # lock, eyes, notify or command
    "intruder-command": "",
    "minimize-apps": [],  # bundle identifiers of the apps to hide
    "minimize-all": False,  # hide every open app, whatever the list says
    "minimize-restore": True,
    "python-path": "",
}

ACTIONS = ("lock", "eyes", "notify", "command")

# Changing one of these needs the daemon to restart.
RESTART_KEYS = frozenset({
    "camera-device", "interval-ms", "model", "use-gpu", "match-thresholds", "detection-threshold",
    "min-face-px", "absence-grace-s", "intruder-grace-s", "python-path",
})


class Settings:
    def __init__(self, path=SETTINGS_PATH):
        self._path = path
        self._values = dict(DEFAULTS)
        self._listeners = []
        self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as handle:
                stored = json.load(handle)
        except (OSError, ValueError):
            return
        if isinstance(stored, dict):
            # Ignores unknown keys, and values of the wrong type.
            for key, default in DEFAULTS.items():
                value = stored.get(key)
                if isinstance(value, type(default)) or (isinstance(default, float) and isinstance(value, int)):
                    self._values[key] = value
            if self._values["intruder-action"] not in ACTIONS:  # e.g. one a newer version had
                self._values["intruder-action"] = DEFAULTS["intruder-action"]

    def get(self, key):
        return self._values[key]

    def set(self, key, value):
        if self._values[key] == value:
            return
        self._values[key] = value
        self._save()
        for listener in list(self._listeners):
            listener(key)

    def on_change(self, listener):
        self._listeners.append(listener)

    def _save(self):
        os.makedirs(os.path.dirname(self._path), mode=0o700, exist_ok=True)
        temporary = f"{self._path}.{os.getpid()}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self._values, handle, indent=2, sort_keys=True)
        os.replace(temporary, self._path)
