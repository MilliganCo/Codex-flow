"""Transactional CLI replacement: a failed render write preserves the old file."""
import os
from pathlib import Path
import tempfile


def write_frame(path: Path, frame: str):
    data = frame.encode("ascii")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=".ascii-tree-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
