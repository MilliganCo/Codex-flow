"""Validation never writes; extraction publishes one fully validated directory."""

from __future__ import annotations

import binascii
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile
from typing import BinaryIO
import zipfile
import zlib


MAX_ENTRIES = 64
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_RATIO = 100
CHUNK_BYTES = 64 * 1024
# A ZIP central record has 46 fixed bytes and three uint16-length fields.
MAX_CENTRAL_BYTES = MAX_ENTRIES * (46 + 3 * 65535)
_COMPONENT = re.compile(r"[A-Za-z0-9._ -]{1,80}\Z", re.ASCII)
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_LOCAL_HEADER = struct.Struct("<4s5H3I2H")


class SafeZipError(Exception):
    """An unsafe, corrupt or unsupported archive, or an extraction failure."""


class _BoundedReader:
    """Prevent zipfile's metadata parser from making an unbounded read."""

    def __init__(self, raw: BinaryIO):
        self.raw = raw

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            position = self.raw.tell()
            self.raw.seek(0, os.SEEK_END)
            size = self.raw.tell() - position
            self.raw.seek(position)
        if size > MAX_CENTRAL_BYTES:
            raise SafeZipError("ZIP metadata exceeds the maximum for 64 entries")
        return self.raw.read(size)

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self.raw.seek(offset, whence)

    def tell(self) -> int:
        return self.raw.tell()

    def seekable(self) -> bool:
        return True


def _canonical_name(info: zipfile.ZipInfo) -> tuple[str, bool]:
    # orig_filename retains embedded NULs which ZipInfo.filename truncates.
    name = info.orig_filename
    is_directory = name.endswith("/")
    path = name[:-1] if is_directory else name
    components = path.split("/")
    for component in components:
        if (
            not _COMPONENT.fullmatch(component)
            or component in (".", "..")
            or component.endswith((".", " "))
            or component.split(".", 1)[0].upper() in _RESERVED
        ):
            raise SafeZipError(f"nonportable member name: {name!r}")

    dos_directory = bool(info.external_attr & 0x10)
    if dos_directory != is_directory:
        raise SafeZipError(f"directory flag disagrees with name: {name!r}")
    unix_type = stat.S_IFMT(info.external_attr >> 16)
    expected_type = stat.S_IFDIR if is_directory else stat.S_IFREG
    if unix_type not in (0, expected_type):
        raise SafeZipError(f"special file or conflicting Unix type: {name!r}")
    return path, is_directory


def _metadata(infos: list[zipfile.ZipInfo]) -> list[tuple[zipfile.ZipInfo, str, bool]]:
    if len(infos) > MAX_ENTRIES:
        raise SafeZipError("archive contains more than 64 entries")
    members = []
    kinds: dict[str, bool] = {}
    total = 0
    for info in infos:
        path, is_directory = _canonical_name(info)
        key = path.casefold()
        if key in kinds:
            raise SafeZipError(f"duplicate path or file/directory collision: {path!r}")
        kinds[key] = is_directory
        if info.flag_bits & (0x1 | 0x40 | 0x2000):
            raise SafeZipError(f"encrypted member: {path!r}")
        if info.flag_bits & 0x20:
            raise SafeZipError(f"patched ZIP data is unsupported: {path!r}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise SafeZipError(f"unsupported compression: {path!r}")
        if info.volume != 0:
            raise SafeZipError("multi-disk ZIP archives are unsupported")
        if is_directory and info.file_size != 0:
            raise SafeZipError(f"directory has a payload: {path!r}")
        if info.file_size > MAX_FILE_BYTES:
            raise SafeZipError(f"member exceeds 512 KiB: {path!r}")
        if info.file_size > 0 and (
            info.compress_size == 0 or info.file_size > MAX_RATIO * info.compress_size
        ):
            raise SafeZipError(f"compression ratio exceeds 100: {path!r}")
        if not is_directory:
            total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise SafeZipError("uncompressed file total exceeds 2 MiB")
        members.append((info, path, is_directory))

    # Check all parents after collecting entries, independent of member order.
    for _, path, _ in members:
        parts = path.casefold().split("/")
        for length in range(1, len(parts)):
            if kinds.get("/".join(parts[:length])) is False:
                raise SafeZipError(f"a file is used as a parent: {path!r}")

    return members


def _read_exact(raw: BinaryIO, size: int) -> bytes:
    data = raw.read(size)
    if len(data) != size:
        raise SafeZipError("truncated ZIP data")
    return data


def _data_start(raw: BinaryIO, info: zipfile.ZipInfo, end: int) -> tuple[int, bool]:
    if info.header_offset < 0 or info.header_offset + _LOCAL_HEADER.size > end:
        raise SafeZipError("invalid local header offset")
    raw.seek(info.header_offset)
    signature, version, flags, method, _, _, crc, compressed, size, nlen, xlen = (
        _LOCAL_HEADER.unpack(_read_exact(raw, _LOCAL_HEADER.size))
    )
    if signature != b"PK\x03\x04":
        raise SafeZipError("invalid local ZIP header")
    if flags != info.flag_bits or method != info.compress_type:
        raise SafeZipError("local and central ZIP headers disagree")
    if version > zipfile.MAX_EXTRACT_VERSION:
        raise SafeZipError("unsupported ZIP extraction version")
    local_name = _read_exact(raw, nlen).decode("utf-8" if flags & 0x800 else "cp437")
    if local_name != info.orig_filename:
        raise SafeZipError("local and central member names disagree")
    extra = _read_exact(raw, xlen)
    # Resolve local ZIP64 size fields when present (including force_zip64 writes).
    zip64 = size == 0xFFFFFFFF or compressed == 0xFFFFFFFF
    if zip64:
        position = 0
        found = False
        while position + 4 <= len(extra):
            tag, length = struct.unpack_from("<HH", extra, position)
            position += 4
            field = extra[position : position + length]
            if len(field) != length:
                raise SafeZipError("truncated ZIP extra field")
            if tag == 1:
                offset = 0
                if size == 0xFFFFFFFF:
                    if len(field) < offset + 8:
                        raise SafeZipError("missing ZIP64 size")
                    size = struct.unpack_from("<Q", field, offset)[0]
                    offset += 8
                if compressed == 0xFFFFFFFF:
                    if len(field) < offset + 8:
                        raise SafeZipError("missing ZIP64 compressed size")
                    compressed = struct.unpack_from("<Q", field, offset)[0]
                found = True
                break
            position += length
        if not found:
            raise SafeZipError("missing ZIP64 extra field")
    if not flags & 0x8 and (crc, compressed, size) != (
        info.CRC, info.compress_size, info.file_size
    ):
        raise SafeZipError("local and central member sizes/CRC disagree")
    start = raw.tell()
    if start + info.compress_size > end:
        raise SafeZipError("overlapping or truncated member data")
    return start, zip64


def _check_descriptor(raw: BinaryIO, info: zipfile.ZipInfo, start: int, end: int, zip64: bool) -> None:
    if not info.flag_bits & 0x8:
        return
    position = start + info.compress_size
    raw.seek(position)
    descriptor = raw.read(min(24, end - position))
    sizes = struct.pack("<QQ" if zip64 else "<II", info.compress_size, info.file_size)
    expected = struct.pack("<I", info.CRC) + sizes
    if not (descriptor.startswith(expected) or descriptor.startswith(b"PK\x07\x08" + expected)):
        raise SafeZipError("data descriptor sizes/CRC disagree with central metadata")


def _payload(raw: BinaryIO, info: zipfile.ZipInfo) -> bytes:
    """Read the complete stream, never trusting its declared uncompressed size."""
    output = bytearray()
    crc = 0
    decoder = zlib.decompressobj(-zlib.MAX_WBITS) if info.compress_type == 8 else None

    def accept(block: bytes) -> None:
        nonlocal crc
        if len(output) + len(block) > min(info.file_size, MAX_FILE_BYTES):
            raise SafeZipError(f"actual payload exceeds declared size/quota: {info.orig_filename!r}")
        output.extend(block)
        crc = binascii.crc32(block, crc)

    remaining = info.compress_size
    while remaining:
        chunk = _read_exact(raw, min(CHUNK_BYTES, remaining))
        remaining -= len(chunk)
        if decoder is None:
            accept(chunk)
        else:
            while chunk:
                # +1 detects an overrun without ever expanding the full bomb.
                limit = min(CHUNK_BYTES, info.file_size - len(output) + 1)
                accept(decoder.decompress(chunk, limit))
                chunk = decoder.unconsumed_tail
                if decoder.unused_data or (decoder.eof and (chunk or remaining)):
                    raise SafeZipError("trailing data after a deflate stream")
    if decoder is not None and not decoder.eof:
        raise SafeZipError("truncated deflate stream")
    if len(output) != info.file_size or crc != info.CRC:
        raise SafeZipError(f"size or CRC mismatch: {info.orig_filename!r}")
    return bytes(output)


def validate_archive(archive: os.PathLike[str] | str, *, keep_payloads: bool = False) -> tuple[dict, dict[str, bytes]]:
    """Return a deterministic manifest and optional bounded file payloads."""
    entries = []
    payloads = {}
    actual_total = 0
    with open(archive, "rb") as raw, zipfile.ZipFile(_BoundedReader(raw), "r") as zipped:
        members = _metadata(zipped.infolist())
        by_offset = sorted(members, key=lambda member: member[0].header_offset)
        boundaries = {}
        for index, (info, _, _) in enumerate(by_offset):
            end = by_offset[index + 1][0].header_offset if index + 1 < len(by_offset) else zipped.start_dir
            if end > zipped.start_dir:
                raise SafeZipError("local header overlaps the central directory")
            boundaries[id(info)] = end
        for info, path, is_directory in members:
            start, zip64 = _data_start(raw, info, boundaries[id(info)])
            data = _payload(raw, info)
            _check_descriptor(raw, info, start, boundaries[id(info)], zip64)
            if not is_directory:
                actual_total += len(data)
                if actual_total > MAX_TOTAL_BYTES:
                    raise SafeZipError("actual file total exceeds 2 MiB")
                if keep_payloads:
                    payloads[path] = data
            entries.append({
                "path": path,
                "kind": "dir" if is_directory else "file",
                "size": 0 if is_directory else len(data),
                "sha256": None if is_directory else hashlib.sha256(data).hexdigest(),
            })
    return {
        "schema": 1,
        "entries": sorted(entries, key=lambda entry: entry["path"]),
        "file_count": sum(entry["kind"] == "file" for entry in entries),
        "total_uncompressed_bytes": actual_total,
    }, payloads


def _rename_absent(source: Path, destination: Path) -> None:
    """Atomic directory publication which cannot replace a racing destination."""
    if os.name == "nt":
        # Windows rename fails if any destination already exists.
        os.rename(source, destination)
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(destination), 4)
    else:
        raise SafeZipError("this platform lacks atomic directory rename without replacement")
    if result != 0:
        code = ctypes.get_errno()
        if code in (errno.ENOSYS, errno.ENOTSUP, errno.EINVAL):
            raise SafeZipError("the filesystem lacks atomic rename without replacement")
        raise OSError(code, os.strerror(code), str(destination))


def extract_archive(archive: os.PathLike[str] | str, destination: os.PathLike[str] | str) -> dict:
    requested = Path(os.path.abspath(destination))
    if os.path.lexists(requested):
        raise SafeZipError("destination already exists")
    parent = requested.parent.resolve(strict=True)
    if not parent.is_dir():
        raise SafeZipError("destination parent must be an existing directory")
    destination_path = parent / requested.name
    if os.path.lexists(destination_path):
        raise SafeZipError("destination already exists")
    manifest, payloads = validate_archive(archive, keep_payloads=True)
    staging = Path(tempfile.mkdtemp(prefix=".safezip-", dir=parent))
    try:
        for entry in manifest["entries"]:
            target = staging.joinpath(*entry["path"].split("/"))
            if entry["kind"] == "dir":
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(payloads[entry["path"]])
        _rename_absent(staging, destination_path)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest
