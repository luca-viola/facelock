"""Where Facelock keeps its files, which differs between Linux and macOS."""

import os
import sys
import tempfile

MACOS = sys.platform == "darwin"
# The macOS app is still called Face Guard.
APP_DIR = "faceguard" if MACOS else "facelock"


def data_home():
    """The folder for the reference photo and the downloaded models."""
    if MACOS:
        return os.path.expanduser("~/Library/Application Support")
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


def runtime_home():
    """A private folder for short-lived files such as the preview frame."""
    if MACOS:
        return tempfile.gettempdir()  # $TMPDIR is per user on macOS
    return os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.cache")
