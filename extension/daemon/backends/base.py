"""What every face-recognition backend provides, so the rest needn't know which runs."""

from dataclasses import dataclass
from typing import Any, Protocol

CPU = "cpu"
GPU = "gpu"


@dataclass(frozen=True)
class DetectedFace:
    """A face found in an image.

    The embedding only means something to the backend that made it, so compare
    embeddings with that backend's similarity().
    """

    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in image pixels
    embedding: Any
    confidence: float | None = None  # None when the detector gives no score
    # The two eyes and the tip of the nose as (x, y), in image pixels, or None. Liveness uses them.
    landmarks: tuple | None = None

    @property
    def size(self):
        """The shorter side of the box, in pixels."""
        x1, y1, x2, y2 = self.box
        return min(x2 - x1, y2 - y1)

    def center(self, image_width, image_height):
        """Where the face is, from 0 to 1 on each axis."""
        x1, y1, x2, y2 = self.box
        return float((x1 + x2) / 2 / image_width), float((y1 + y2) / 2 / image_height)


class FaceBackend(Protocol):
    compute: str  # CPU or GPU: what actually runs, which may differ from what was asked

    def faces(self, image) -> list[DetectedFace]:
        """Finds the faces in a BGR image."""

    def similarity(self, a, b) -> float:
        """Compares two embeddings. Higher means more alike."""

    def warm_up(self) -> None:
        """Runs the models once, since the first run can be much slower."""
