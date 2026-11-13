"""macOS cameras through AVFoundation, opened with OpenCV.

OpenCV's AVFoundation backend opens a camera by its position in the system's
list, which changes when cameras come and go. So a camera is stored by its
AVFoundation unique ID, and turned into a position only when it is opened.
"""

from errors import GuardError

# Names of software cameras, which show no one and should never be picked by "auto".
VIRTUAL_NAMES = ("obs", "virtual", "snap camera", "camtwist", "ndi", "mmhmm", "epoccam", "droidcam",
                 "screen capture", "desk view")


def _av():
    import AVFoundation

    return AVFoundation


def authorization():
    """One of "authorized", "denied", "restricted" or "undetermined"."""
    av = _av()
    status = av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo)
    return {
        av.AVAuthorizationStatusAuthorized: "authorized",
        av.AVAuthorizationStatusDenied: "denied",
        av.AVAuthorizationStatusRestricted: "restricted",
    }.get(status, "undetermined")


def _devices():
    av = _av()
    devices = list(av.AVCaptureDevice.devicesWithMediaType_(av.AVMediaTypeVideo) or [])
    devices += list(av.AVCaptureDevice.devicesWithMediaType_(av.AVMediaTypeMuxed) or [])
    return devices


def _is_virtual(name):
    lowered = name.lower()
    return any(word in lowered for word in VIRTUAL_NAMES)


def list_cameras():
    """Cameras in the order OpenCV numbers them, with the unique ID as the path."""
    return [
        {"path": str(device.uniqueID()), "name": str(device.localizedName()),
         "virtual": _is_virtual(str(device.localizedName()))}
        for device in _devices()
    ]


def _index_of(device):
    if device.isdigit():
        return int(device)
    for index, camera in enumerate(list_cameras()):
        if camera["path"] == device:
            return index
    raise GuardError("camera", f"Camera {device} isn't connected", retryable=True)


def open_capture(device, width, height):
    """Opens a camera by unique ID, asking for the given size."""
    import cv2

    status = authorization()
    if status in ("denied", "restricted"):
        raise GuardError("camera_permission",
                         "Camera access is off for Face Guard. Allow it in System Settings, Privacy & Security, Camera.",
                         retryable=False)
    capture = cv2.VideoCapture(_index_of(device), cv2.CAP_AVFOUNDATION)
    if not capture.isOpened():
        capture.release()
        raise GuardError("camera", f"Can't open camera {device}", retryable=True)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture
