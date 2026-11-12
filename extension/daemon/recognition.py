"""Telling the owner from everyone else in a set of detected faces."""

from errors import GuardError


def classify_faces(faces, reference, similarity, match_threshold, min_face_px):
    """Returns (owner present, the other faces, best match score or None).

    Only the best match can be the owner, so a second face scoring above the
    threshold still counts as another person.
    """
    candidates = [face for face in faces if face.size >= min_face_px]
    if not candidates:
        return False, [], None
    scores = [similarity(face.embedding, reference) for face in candidates]
    best = max(scores)
    if best >= match_threshold:
        owner = scores.index(best)
        return True, candidates[:owner] + candidates[owner + 1:], best
    return False, candidates, best


def load_reference(backend, path):
    """Returns the owner's embedding from the reference image."""
    import cv2

    image = cv2.imread(path)
    if image is None:
        raise GuardError("no_reference", f"Can't read the reference image {path}", retryable=False)
    faces = backend.faces(image)
    if len(faces) != 1:
        raise GuardError(
            "bad_reference",
            f"The reference image must show exactly one face, found {len(faces)}",
            retryable=False,
        )
    return faces[0].embedding
