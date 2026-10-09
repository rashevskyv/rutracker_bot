"""Atomic file writes: readers (and the Gist uploader) never see a half-written state file."""
import os
import tempfile
from contextlib import contextmanager


@contextmanager
def atomic_open(path, encoding: str = "utf-8"):
    """Open a temp file next to path for text writing; replace path with it only after a clean close."""
    path = os.fspath(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=f".{os.path.basename(path)}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            yield f
            f.flush()
            os.fsync(f.fileno())
        # mkstemp creates 0600; keep the replaced file's permissions.
        try:
            os.chmod(tmp_path, os.stat(path).st_mode & 0o777)
        except FileNotFoundError:
            os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
