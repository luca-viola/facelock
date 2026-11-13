"""dlib: a HOG or CNN face detector, with dlib's ResNet face recognizer."""

import os

from .base import CPU, GPU, DetectedFace
from .model_files import fetch_bz2, model_path

BASE_URL = "https://dlib.net/files"
RECOGNIZER = "dlib_face_recognition_resnet_model_v1.dat"
LANDMARKS = "shape_predictor_5_face_landmarks.dat"  # aligns faces for the recognizer
CNN_DETECTOR = "mmod_human_face_detector.dat"
HOG = "hog"
CNN = "cnn"
FILES = {HOG: (RECOGNIZER, LANDMARKS), CNN: (RECOGNIZER, LANDMARKS, CNN_DETECTOR)}

# Detection runs on a smaller copy of the frame, since its time grows with the area.
# dlib's detectors find faces from about 80 pixels across at the size they're given.
DETECTION_WIDTH = {HOG: 1280, CNN: 960}


def installed():
    """Whether dlib can be imported. Being present isn't enough: a build that links a library
    which isn't there is found by find_spec and then fails to load."""
    try:
        import dlib  # noqa: F401
    except ImportError:
        return False
    return True


def _path(filename):
    return model_path("dlib", filename)


def files_present(detector):
    return all(os.path.exists(_path(filename)) for filename in FILES[detector])


def download_files(detector):
    for filename in FILES[detector]:
        if not os.path.exists(_path(filename)):
            fetch_bz2(f"{BASE_URL}/{filename}.bz2", _path(filename))


class DlibBackend:
    def __init__(self, detector):
        import dlib

        download_files(detector)
        self._kind = detector
        if detector == CNN:
            self._detector = dlib.cnn_face_detection_model_v1(_path(CNN_DETECTOR))
        else:
            self._detector = dlib.get_frontal_face_detector()
        self._landmarks = dlib.shape_predictor(_path(LANDMARKS))
        self._recognizer = dlib.face_recognition_model_v1(_path(RECOGNIZER))
        # A CUDA build of dlib always uses the GPU, so report what it really does.
        self.compute = GPU if dlib.DLIB_USE_CUDA else CPU

    def _detect(self, rgb):
        """Returns (dlib rectangle in rgb's pixels, confidence) for each face."""
        import cv2
        import dlib

        height, width = rgb.shape[:2]
        scale = min(1.0, DETECTION_WIDTH[self._kind] / width)
        small = rgb if scale == 1.0 else cv2.resize(rgb, (round(width * scale), round(height * scale)))
        if self._kind == CNN:
            found = [(d.rect, d.confidence) for d in self._detector(small, 0)]
        else:
            rects, scores, _ = self._detector.run(small, 0, 0.0)
            found = list(zip(rects, scores))
        return [
            (dlib.rectangle(round(r.left() / scale), round(r.top() / scale),
                            round(r.right() / scale), round(r.bottom() / scale)), float(confidence))
            for r, confidence in found
        ]

    def faces(self, image):
        import numpy as np

        rgb = np.ascontiguousarray(image[:, :, ::-1])  # dlib expects RGB; OpenCV gives BGR
        found = []
        for rect, confidence in self._detect(rgb):
            shape = self._landmarks(rgb, rect)
            descriptor = np.array(self._recognizer.compute_face_descriptor(rgb, shape))
            found.append(DetectedFace(
                box=(float(rect.left()), float(rect.top()), float(rect.right()), float(rect.bottom())),
                embedding=descriptor,
                confidence=confidence,
            ))
        return found

    def similarity(self, a, b):
        # dlib compares descriptors by distance, with 0.6 as its usual cut-off. As
        # 1 - distance, higher means more alike like the other models, and the cut-off
        # becomes 0.4.
        import numpy as np

        return 1.0 - float(np.linalg.norm(a - b))

    def warm_up(self):
        import numpy as np

        self.faces(np.zeros((720, 1280, 3), np.uint8))
