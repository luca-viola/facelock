"""The macOS Camera permission (TCC), through AVFoundation.

macOS attributes it to the app that started the daemon. Run from a terminal, that is the
terminal app, which is asked instead of Face Guard.
"""

import subprocess

SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"


def camera_status():
    """One of "authorized", "denied", "restricted" or "undetermined". Doesn't prompt."""
    import AVFoundation as av

    status = av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo)
    return {
        av.AVAuthorizationStatusAuthorized: "authorized",
        av.AVAuthorizationStatusDenied: "denied",
        av.AVAuthorizationStatusRestricted: "restricted",
    }.get(status, "undetermined")


def request_camera_access(on_result):
    """Prompts the first time. on_result(granted) runs on a background thread."""
    import AVFoundation as av

    av.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        av.AVMediaTypeVideo, lambda granted: on_result(bool(granted)))


def open_camera_settings():
    subprocess.run(["open", SETTINGS_URL])
