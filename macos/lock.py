"""Locking the screen. macOS has no public API for it."""

import ctypes
import subprocess

LOGIN_FRAMEWORK = "/System/Library/PrivateFrameworks/login.framework/login"


def lock_screen():
    """Locks at once. Falls back to sleeping the display, which locks only if the
    password is required immediately (System Settings, Lock Screen)."""
    try:
        ctypes.CDLL(LOGIN_FRAMEWORK).SACLockScreenImmediate()
        return
    except (OSError, AttributeError):
        pass
    subprocess.run(["/usr/bin/pmset", "displaysleepnow"], check=True)
