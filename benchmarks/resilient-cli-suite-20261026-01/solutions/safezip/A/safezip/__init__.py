"""SafeZip: bounded, portable ZIP inspection and transactional extraction."""

from .core import SafeZipError, extract_archive, inspect_archive, manifest_bytes

__all__ = ["SafeZipError", "extract_archive", "inspect_archive", "manifest_bytes"]
__version__ = "1.0"
