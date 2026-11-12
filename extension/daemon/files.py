"""Files only the user can read, for images of their face."""

import os


def private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def write_private(path, data):
    """Writes a file readable only by the user, replacing any old one atomically."""
    temporary = f"{path}.{os.getpid()}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.replace(temporary, path)
