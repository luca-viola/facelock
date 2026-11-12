"""Downloading model files that no library downloads for us."""

import bz2
import os
import shutil
import urllib.request

DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
MODEL_DIR = os.path.join(DATA_HOME, "faceguard", "models")
TIMEOUT_S = 60


def model_path(subdir, filename):
    return os.path.join(MODEL_DIR, subdir, filename)


def fetch_bz2(url, destination):
    """Downloads a .bz2 file and stores it unpacked, so a failure never leaves half a file."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temporary = f"{destination}.{os.getpid()}.part"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response, open(temporary, "wb") as out:
            shutil.copyfileobj(bz2.BZ2File(response), out)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
