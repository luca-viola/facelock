"""InsightFace model packs: a detector and a recognizer from the buffalo family."""

import contextlib
import glob
import importlib.util
import os
import sys

from .base import CPU, GPU, DetectedFace
from .onnx_sessions import create_session

MODEL_ROOT = os.path.expanduser("~/.insightface/models")
DETECTION_SIZE = (640, 640)  # 320 is faster but misses the small faces of people further back

# Only these two files of each pack are used; the packs also hold landmark and age models.
PACKS = {
    "buffalo_l": ("det_10g.onnx", "w600k_r50.onnx"),
    "buffalo_m": ("det_2.5g.onnx", "w600k_r50.onnx"),
    "buffalo_sc": ("det_500m.onnx", "w600k_mbf.onnx"),
}


def installed():
    return importlib.util.find_spec("insightface") is not None


def _find(pack, filename):
    matches = glob.glob(os.path.join(MODEL_ROOT, pack, "**", filename), recursive=True)
    return matches[0] if matches else None


def pack_present(pack):
    return all(_find(pack, filename) for filename in PACKS[pack])


def download_pack(pack):
    """Downloads and unpacks a pack, then deletes the zip, which is as big as the pack."""
    from insightface.utils import storage

    # InsightFace skips any pack whose folder exists, even half unpacked.
    with contextlib.redirect_stdout(sys.stderr):
        storage.download("models", pack, force=os.path.isdir(os.path.join(MODEL_ROOT, pack)),
                         root=os.path.dirname(MODEL_ROOT))
    zip_path = os.path.join(MODEL_ROOT, f"{pack}.zip")
    if pack_present(pack) and os.path.exists(zip_path):
        os.remove(zip_path)


class InsightFaceBackend:
    def __init__(self, pack, detection_threshold, compute):
        from insightface.model_zoo.arcface_onnx import ArcFaceONNX
        from insightface.model_zoo.scrfd import SCRFD

        if not pack_present(pack):
            download_pack(pack)
        detector_path, recognizer_path = (_find(pack, filename) for filename in PACKS[pack])
        detector_session, detector_compute = create_session(detector_path, compute)
        recognizer_session, recognizer_compute = create_session(recognizer_path, compute)
        self._detector = SCRFD(detector_path, detector_session)
        self._detector.prepare(0, input_size=DETECTION_SIZE, det_thresh=detection_threshold)
        self._recognizer = ArcFaceONNX(recognizer_path, recognizer_session)
        self._recognizer.prepare(0)
        self.compute = GPU if GPU in (detector_compute, recognizer_compute) else CPU

    def faces(self, image):
        import numpy as np
        from insightface.app.common import Face

        boxes, landmarks = self._detector.detect(image, max_num=0, metric="default")
        found = []
        for box, points in zip(boxes, landmarks):
            face = Face(bbox=box[:4], kps=points, det_score=box[4])
            embedding = self._recognizer.get(image, face)  # aligns the face using the landmarks
            found.append(DetectedFace(
                box=tuple(float(v) for v in box[:4]),
                embedding=embedding / np.linalg.norm(embedding),
                confidence=float(box[4]),
                # The detector's five points are the eyes, the nose and the corners of the mouth.
                landmarks=tuple((float(x), float(y)) for x, y in points[:3]),
            ))
        return found

    def similarity(self, a, b):
        # Both are normalized, so this is their cosine similarity.
        return float(a.dot(b))

    def warm_up(self):
        import numpy as np

        self._detector.detect(np.zeros((720, 1280, 3), np.uint8), max_num=0, metric="default")
        self._recognizer.get_feat(np.zeros((112, 112, 3), np.uint8))
