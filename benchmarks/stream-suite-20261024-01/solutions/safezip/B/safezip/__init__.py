"""Offline, bounded ZIP inspection and transactional extraction."""

from .core import SafeZipError, extract_archive, inspect_archive, manifest_json

__all__ = ["SafeZipError", "extract_archive", "inspect_archive", "manifest_json"]
__version__ = "1.0.0"
