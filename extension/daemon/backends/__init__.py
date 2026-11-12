"""The face-recognition models Face Guard can use, and loading one of them."""

import logging
from dataclasses import dataclass
from typing import Callable

from errors import GuardError

from .base import CPU, GPU, DetectedFace, FaceBackend

log = logging.getLogger("faceguard")


@dataclass(frozen=True)
class Model:
    id: str
    label: str
    download_note: str  # shown while it downloads the first time
    present: Callable[[], bool]  # whether its files are already on disk
    create: Callable[[float], FaceBackend]  # takes the detection threshold


def _insightface(pack, label, download_note):
    from .insightface_backend import InsightFaceBackend, pack_present

    return Model(
        id=pack,
        label=label,
        download_note=download_note,
        present=lambda: pack_present(pack),
        create=lambda detection_threshold: InsightFaceBackend(pack, detection_threshold),
    )


MODELS = {model.id: model for model in (
    _insightface("buffalo_l", "InsightFace large", "a few hundred MB"),
)}


def load_backend(model, detection_threshold, emit):
    """Loads a model, saying what's happening since it can take minutes the first time."""
    present = model.present()
    if present:
        emit("loading", detail="Loading face models. The first run can take a minute.")
    else:
        emit("loading", detail=f"Downloading the {model.id} face models, {model.download_note}.")
    try:
        return model.create(detection_threshold)
    except Exception as error:
        log.exception("Couldn't load %s", model.id)
        message = (f"Couldn't load {model.id}: {error}" if present
                   else f"Couldn't download the {model.id} face models. Check your connection.")
        raise GuardError("model", message, retryable=True) from error
