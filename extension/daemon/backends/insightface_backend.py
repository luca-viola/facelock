"""InsightFace model packs, such as buffalo_l."""

import os

from .base import CPU, GPU, DetectedFace

MODEL_ROOT = os.path.expanduser("~/.insightface/models")
CUDA_PROVIDER = "CUDAExecutionProvider"
CPU_PROVIDER = "CPUExecutionProvider"
DETECTION_SIZE = (640, 640)


def pack_present(pack):
    try:
        return any(name.endswith(".onnx") for name in os.listdir(os.path.join(MODEL_ROOT, pack)))
    except OSError:
        return False


class InsightFaceBackend:
    def __init__(self, pack, detection_threshold):
        import onnxruntime
        from insightface.app import FaceAnalysis

        available = onnxruntime.get_available_providers()
        providers = [p for p in (CUDA_PROVIDER, CPU_PROVIDER) if p in available]
        # Landmarks and gender/age would run on every face for nothing.
        self._app = FaceAnalysis(name=pack, allowed_modules=["detection", "recognition"], providers=providers)
        self._app.prepare(ctx_id=0, det_thresh=detection_threshold, det_size=DETECTION_SIZE)
        provider = self._app.models["recognition"].session.get_providers()[0]
        self.compute = GPU if provider == CUDA_PROVIDER else CPU

    def faces(self, image):
        return [
            DetectedFace(box=tuple(float(v) for v in face.bbox), embedding=face.normed_embedding,
                         confidence=float(face.det_score))
            for face in self._app.get(image)
        ]

    def similarity(self, a, b):
        # Both are normalized, so this is their cosine similarity.
        return float(a.dot(b))

    def warm_up(self):
        import numpy as np

        self._app.get(np.zeros((720, 1280, 3), np.uint8))
        self._app.models["recognition"].get_feat(np.zeros((112, 112, 3), np.uint8))
