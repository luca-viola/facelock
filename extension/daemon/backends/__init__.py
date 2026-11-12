"""The face-recognition models Face Guard can use, and loading one of them."""

import logging
from dataclasses import dataclass
from typing import Callable

from errors import GuardError

from .base import CPU, GPU, DetectedFace, FaceBackend
from .devices import cuda_gpu_name

__all__ = ["CPU", "GPU", "DEFAULT_MODEL", "MODELS", "DetectedFace", "FaceBackend", "Model",
           "cuda_gpu_name", "describe_models", "load_backend"]

log = logging.getLogger("faceguard")


@dataclass(frozen=True)
class Model:
    id: str
    label: str
    download_note: str  # shown while it downloads the first time
    default_match_threshold: float
    uses_detection_threshold: bool
    installed: Callable[[], bool]  # whether its library is installed
    can_use_gpu: Callable[[], bool]  # whether its library was built with GPU support
    present: Callable[[], bool]  # whether its files are already on disk
    create: Callable[[float, str], FaceBackend]  # takes the detection threshold and CPU or GPU


def _insightface(pack, label, download_note):
    from . import insightface_backend, onnx_sessions

    return Model(
        id=pack,
        label=label,
        download_note=download_note,
        default_match_threshold=0.4,
        uses_detection_threshold=True,
        installed=lambda: True,  # Face Guard's environment always has it
        can_use_gpu=onnx_sessions.cuda_provider_available,
        present=lambda: insightface_backend.pack_present(pack),
        create=lambda detection_threshold, compute: insightface_backend.InsightFaceBackend(
            pack, detection_threshold, compute),
    )


MODELS = {model.id: model for model in (
    _insightface("buffalo_l", "buffalo_l, large", "about 280 MB"),
    _insightface("buffalo_m", "buffalo_m, medium", "about 270 MB"),
    _insightface("buffalo_sc", "buffalo_sc, small", "about 15 MB"),
)}
DEFAULT_MODEL = "buffalo_l"


def describe_models():
    """What Settings needs to offer the models and the GPU switch."""
    gpu_name = cuda_gpu_name()
    return {
        "gpu": gpu_name,
        "models": [
            {
                "id": model.id,
                "label": model.label,
                "installed": model.installed(),
                "downloaded": model.installed() and model.present(),
                "gpu": gpu_name is not None and model.installed() and model.can_use_gpu(),
                "default_match_threshold": model.default_match_threshold,
                "uses_detection_threshold": model.uses_detection_threshold,
            }
            for model in MODELS.values()
        ],
    }


def load_backend(model, detection_threshold, compute, emit):
    """Loads a model, saying what's happening since it can take minutes the first time."""
    if not model.installed():
        raise GuardError("model", f"{model.label} isn't installed in Face Guard's Python", retryable=False)
    present = model.present()
    if present:
        emit("loading", detail="Loading face models. The first run can take a minute.")
    else:
        emit("loading", detail=f"Downloading the {model.id} face models, {model.download_note}.")
    try:
        return model.create(detection_threshold, compute)
    except Exception as error:
        log.exception("Couldn't load %s", model.id)
        message = (f"Couldn't load {model.id}: {error}" if present
                   else f"Couldn't download the {model.id} face models. Check your connection.")
        raise GuardError("model", message, retryable=True) from error
