"""Checking an image of the owner and storing it as the reference."""

import os

from errors import GuardError
from files import private_dir, write_private


def enroll(backend, source, reference_path, emit):
    import cv2

    image = cv2.imread(source)
    if image is None:
        raise GuardError("bad_reference", f"Can't read {source} as an image", retryable=False)
    faces = backend.faces(image)
    if not faces:
        raise GuardError("bad_reference", "No face found in that image", retryable=False)
    if len(faces) > 1:
        raise GuardError("bad_reference",
                         f"Found {len(faces)} faces. Use an image with only yours.", retryable=False)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise GuardError("bad_reference", "Couldn't encode that image", retryable=False)
    private_dir(os.path.dirname(reference_path))
    write_private(reference_path, encoded.tobytes())
    confidence = faces[0].confidence
    emit("enrolled", path=reference_path,
         detection_score=None if confidence is None else round(confidence, 3))
