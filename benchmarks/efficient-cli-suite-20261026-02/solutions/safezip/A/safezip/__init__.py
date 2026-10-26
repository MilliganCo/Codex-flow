"""Safe, bounded ZIP inspection and transactional extraction (standard library only)."""

from .core import SafeZipError, extract_archive, inspect_archive, manifest_bytes

__all__ = ["SafeZipError", "extract_archive", "inspect_archive", "manifest_bytes"]
