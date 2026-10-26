"""ZIP validation, bounded streaming, and no-replace directory publication.

Archive metadata and local headers are checked before any payload is expanded.
Payloads are decoded directly rather than through ZipExtFile: ZipExtFile trusts
the advertised uncompressed length, which can conceal excess deflated output.
"""

from __future__ import annotations

import binascii
import ctypes
from dataclasses import dataclass
import errno
import hashlib
import json
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
_COMPONENT = re.compile(r"[A-Za-z0-9._ -]{1,80}\Z", re.ASCII)
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


class SafeZipError(Exception):
    """An invalid archive or an operation that cannot be completed safely."""


@dataclass(frozen=True)
class _Member:
    info: zipfile.ZipInfo
    path: str
    kind: str
    data_offset: int


def manifest_bytes(manifest: dict) -> bytes:
    """Return the exact canonical UTF-8 wire representation."""
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _exact(source: BinaryIO, length: int) -> bytes:
    data = source.read(length)
    if len(data) != length:
        raise SafeZipError("truncated ZIP structure or payload")
    return data


def _preflight(source: BinaryIO) -> tuple[int, int]:
    """Bound central-directory parsing before ZipFile allocates its index.

Only a ZIP comment-sized tail and fixed-size records are read. Scanning stops
at entry 65, even if an archive lies about its central-directory entry count.
Small ZIP64 archives and self-extracting prefixes are supported as data.
"""
    source.seek(0, os.SEEK_END)
    length = source.tell()
    tail_length = min(length, 22 + 65535)
    source.seek(length - tail_length)
    tail = _exact(source, tail_length)
    position = tail.rfind(b"PK\x05\x06")
    while position >= 0:
        if position + 22 <= len(tail):
            comment_length = struct.unpack_from("<H", tail, position + 20)[0]
            if position + 22 + comment_length == len(tail):
                break
        position = tail.rfind(b"PK\x05\x06", 0, position)
    if position < 0:
        raise SafeZipError("missing or damaged ZIP end record")
    end_position = length - tail_length + position
    (_, disk, central_disk, disk_count, count, central_size,
     central_offset, _) = struct.unpack_from("<4s4H2IH", tail, position)
    if disk or central_disk or disk_count != count:
        raise SafeZipError("multi-disk ZIP archives are not supported")
    central_end = end_position

    # ZIP64's locator immediately precedes the ordinary end record.
    locator = b""
    if end_position >= 20:
        source.seek(end_position - 20)
        locator = _exact(source, 20)
    if locator.startswith(b"PK\x06\x07"):
        _, locator_disk, zip64_offset, disks = struct.unpack("<4sIQI", locator)
        if locator_disk or disks != 1:
            raise SafeZipError("multi-disk ZIP64 archives are not supported")
        zip64 = None
        for candidate in (end_position - 20 - 56, zip64_offset):
            if candidate < 0 or candidate + 56 > end_position - 20:
                continue
            source.seek(candidate)
            record = _exact(source, 56)
            if record[:4] != b"PK\x06\x06":
                continue
            values = struct.unpack("<4sQ2H2I4Q", record)
            if values[1] >= 44 and candidate + 12 + values[1] == end_position - 20:
                zip64 = values
                central_end = candidate
                break
        if zip64 is None:
            raise SafeZipError("damaged ZIP64 end record")
        (_, _, _, _, disk, central_disk, disk_count, count,
         central_size, central_offset) = zip64
        if disk or central_disk or disk_count != count:
            raise SafeZipError("multi-disk ZIP64 archives are not supported")
    elif count == 0xFFFF or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF:
        raise SafeZipError("missing ZIP64 end record")

    if count > MAX_ENTRIES:
        raise SafeZipError(f"archive exceeds {MAX_ENTRIES} entries")
    central_start = central_end - central_size
    if central_start < 0 or central_offset > central_start:
        raise SafeZipError("invalid central-directory bounds")
    source.seek(central_start)
    actual_count = 0
    while source.tell() < central_end:
        actual_count += 1
        if actual_count > MAX_ENTRIES:
            raise SafeZipError(f"archive exceeds {MAX_ENTRIES} entries")
        if central_end - source.tell() < 46:
            raise SafeZipError("truncated central directory")
        header = _exact(source, 46)
        if header[:4] != b"PK\x01\x02":
            raise SafeZipError("invalid central-directory entry")
        name_length, extra_length, comment_length, member_disk = struct.unpack_from(
            "<4H", header, 28)
        if member_disk:
            raise SafeZipError("multi-disk ZIP members are not supported")
        end = source.tell() + name_length + extra_length + comment_length
        if end > central_end:
            raise SafeZipError("central-directory entry exceeds its bounds")
        source.seek(end)
    if actual_count != count:
        raise SafeZipError("central-directory entry count disagrees with end record")
    return central_start, count


def _portable_name(name: str) -> tuple[str, str]:
    is_directory = name.endswith("/")
    path = name[:-1] if is_directory else name
    for component in path.split("/"):
        if (not _COMPONENT.fullmatch(component) or component in {".", ".."}
                or component.endswith((".", " "))):
            raise SafeZipError(f"nonportable member name: {name!r}")
        # Strip spaces before the first extension as well: Windows treats
        # names such as 'CON .txt' as device names on some filesystem APIs.
        if component.split(".", 1)[0].rstrip(" ").upper() in _RESERVED:
            raise SafeZipError(f"reserved member name: {name!r}")
    return path, "dir" if is_directory else "file"


def _check_flags(flags: int) -> None:
    if flags & (0x0001 | 0x0040 | 0x2000):
        raise SafeZipError("encrypted ZIP members are not supported")
    if flags & ~0x080E:
        raise SafeZipError("unsupported ZIP member flags")


def _local_sizes(size: int, compressed: int, extra: bytes) -> tuple[int, int]:
    if size != 0xFFFFFFFF and compressed != 0xFFFFFFFF:
        return size, compressed
    position = 0
    while position + 4 <= len(extra):
        tag, length = struct.unpack_from("<HH", extra, position)
        position += 4
        if position + length > len(extra):
            raise SafeZipError("truncated local ZIP extra field")
        if tag == 1:
            values = extra[position:position + length]
            offset = 0
            if size == 0xFFFFFFFF:
                if len(values) < 8:
                    raise SafeZipError("missing ZIP64 local size")
                size = struct.unpack_from("<Q", values, offset)[0]
                offset += 8
            if compressed == 0xFFFFFFFF:
                if len(values) < offset + 8:
                    raise SafeZipError("missing ZIP64 local compressed size")
                compressed = struct.unpack_from("<Q", values, offset)[0]
            return size, compressed
        position += length
    raise SafeZipError("missing ZIP64 local extra field")


def _local_header(source: BinaryIO, info: zipfile.ZipInfo, end: int) -> int:
    if info.header_offset < 0 or info.header_offset + 30 > end:
        raise SafeZipError("overlapping or invalid local ZIP header")
    source.seek(info.header_offset)
    (signature, _, flags, method, _, _, crc, compressed, size,
     name_length, extra_length) = struct.unpack("<4s5H3I2H", _exact(source, 30))
    if signature != b"PK\x03\x04":
        raise SafeZipError("invalid local ZIP header")
    _check_flags(flags)
    if flags != info.flag_bits or method != info.compress_type:
        raise SafeZipError("local and central ZIP headers disagree")
    data_offset = source.tell() + name_length + extra_length
    if data_offset > end or info.compress_size > end - data_offset:
        raise SafeZipError("overlapping or truncated ZIP member data")
    name = _exact(source, name_length).decode("utf-8" if flags & 0x800 else "cp437")
    if name != info.orig_filename:
        raise SafeZipError("local and central member names disagree")
    extra = _exact(source, extra_length)
    if not flags & 0x08:
        size, compressed = _local_sizes(size, compressed, extra)
        if (size, compressed, crc) != (info.file_size, info.compress_size, info.CRC):
            raise SafeZipError("local and central member sizes or CRC disagree")
    return data_offset


def _members(source: BinaryIO, archive: zipfile.ZipFile,
             central_start: int, expected_count: int) -> list[_Member]:
    infos = archive.infolist()
    if len(infos) != expected_count or len(infos) > MAX_ENTRIES:
        raise SafeZipError("invalid ZIP entry count")
    names: dict[str, str] = {}
    parsed: list[tuple[zipfile.ZipInfo, str, str]] = []
    total = 0
    for info in infos:
        _check_flags(info.flag_bits)
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise SafeZipError("only stored and deflated members are supported")
        path, kind = _portable_name(info.orig_filename)
        mode_type = stat.S_IFMT(info.external_attr >> 16)
        directory_flag = bool(info.external_attr & 0x10)
        is_directory = kind == "dir"
        if mode_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise SafeZipError(f"symlink or special-file member: {path!r}")
        if directory_flag != is_directory or (
                mode_type and (mode_type == stat.S_IFDIR) != is_directory):
            raise SafeZipError(f"member type and directory flag/name disagree: {path!r}")
        key = path.casefold()
        if key in names:
            raise SafeZipError(f"case-insensitive duplicate or collision: {path!r}")
        names[key] = kind
        if info.file_size < 0 or info.compress_size < 0:
            raise SafeZipError("negative ZIP size")
        if is_directory and info.file_size != 0:
            raise SafeZipError("explicit directories must have empty payloads")
        if info.file_size > MAX_FILE_BYTES:
            raise SafeZipError(f"member exceeds {MAX_FILE_BYTES} bytes: {path!r}")
        if info.file_size and (not info.compress_size
                               or info.file_size > MAX_RATIO * info.compress_size):
            raise SafeZipError(f"member exceeds compression ratio {MAX_RATIO}: {path!r}")
        if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
            raise SafeZipError("stored member sizes disagree")
        if not is_directory:
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise SafeZipError(f"archive exceeds {MAX_TOTAL_BYTES} uncompressed bytes")
        parsed.append((info, path, kind))

    # Check all ancestors after collecting all names: order cannot hide a file
    # used as a directory, including differences in ASCII letter case.
    for _, path, _ in parsed:
        components = path.casefold().split("/")
        for depth in range(1, len(components)):
            if names.get("/".join(components[:depth])) == "file":
                raise SafeZipError(f"file used as a parent directory: {path!r}")

    offsets = sorted(info.header_offset for info in infos)
    if len(set(offsets)) != len(offsets):
        raise SafeZipError("members share a local ZIP header")
    ends = dict(zip(offsets, offsets[1:] + [central_start]))
    return [_Member(info, path, kind, _local_header(source, info, ends[info.header_offset]))
            for info, path, kind in parsed]


def _payload(source: BinaryIO, member: _Member, sink: BinaryIO | None,
             previous_total: int) -> tuple[int, str]:
    info = member.info
    source.seek(member.data_offset)
    remaining = info.compress_size
    produced = 0
    crc = 0
    digest = hashlib.sha256()

    def consume(data: bytes) -> None:
        nonlocal produced, crc
        produced += len(data)
        if (produced > info.file_size or produced > MAX_FILE_BYTES
                or previous_total + produced > MAX_TOTAL_BYTES
                or (produced and produced > MAX_RATIO * info.compress_size)):
            raise SafeZipError(f"actual payload exceeds declared size or quota: {member.path!r}")
        crc = binascii.crc32(data, crc)
        digest.update(data)
        if sink is not None:
            sink.write(data)

    if info.compress_type == zipfile.ZIP_STORED:
        while remaining:
            data = _exact(source, min(CHUNK_BYTES, remaining))
            remaining -= len(data)
            consume(data)
    else:
        decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        while remaining:
            chunk = _exact(source, min(CHUNK_BYTES, remaining))
            remaining -= len(chunk)
            while chunk:
                # One byte beyond the declared size detects dishonest metadata
                # without allowing an unbounded decompression allocation.
                limit = min(CHUNK_BYTES, info.file_size - produced + 1)
                consume(decoder.decompress(chunk, limit))
                if decoder.unused_data or (decoder.eof and remaining):
                    raise SafeZipError("trailing bytes after deflated payload")
                chunk = decoder.unconsumed_tail
        while not decoder.eof:
            data = decoder.decompress(b"", min(CHUNK_BYTES, info.file_size - produced + 1))
            if not data:
                break
            consume(data)
        if not decoder.eof or decoder.unused_data:
            raise SafeZipError("truncated or invalid deflated payload")
    if produced != info.file_size:
        raise SafeZipError(f"actual and declared sizes disagree: {member.path!r}")
    if crc & 0xFFFFFFFF != info.CRC:
        raise SafeZipError(f"CRC mismatch: {member.path!r}")
    return produced, digest.hexdigest()


def _manifest(source: BinaryIO, members: list[_Member], stage: Path | None) -> dict:
    entries = []
    total = 0
    file_count = 0
    for member in members:
        target = stage.joinpath(*member.path.split("/")) if stage is not None else None
        if member.kind == "dir":
            _payload(source, member, None, total)
            if target is not None:
                target.mkdir(parents=True, exist_ok=True)
            size, digest = 0, None
        else:
            if target is None:
                size, digest = _payload(source, member, None, total)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as sink:
                    size, digest = _payload(source, member, sink, total)
            total += size
            file_count += 1
        entries.append({"path": member.path, "kind": member.kind,
                        "size": size, "sha256": digest})
    return {"schema": 1, "entries": sorted(entries, key=lambda entry: entry["path"]),
            "file_count": file_count, "total_uncompressed_bytes": total}


def _destination(destination: str | os.PathLike[str]) -> Path:
    path = Path(os.path.abspath(destination))
    if os.path.lexists(path):
        raise SafeZipError("destination already exists; choose an absent directory")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise SafeZipError("destination parent must be an existing directory")
    path = parent / path.name
    if os.path.lexists(path):
        raise SafeZipError("destination already exists; choose an absent directory")
    return path


def _commit(stage: Path, destination: Path) -> None:
    """Atomically rename a complete directory without ever replacing a target.

    POSIX os.rename can replace an existing empty directory. Use the OS's
    exclusive rename operation instead; ctypes is part of the standard library.
    Fail closed on a platform/filesystem without that operation.
    """
    if sys.platform == "win32":
        os.rename(stage, destination)  # Windows rename always refuses replacement.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux"):
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise SafeZipError("this platform lacks atomic no-replace rename")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                           ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(stage), -100, os.fsencode(destination), 1)
    elif sys.platform == "darwin":
        rename = getattr(libc, "renamex_np", None)
        if rename is None:
            raise SafeZipError("this platform lacks atomic no-replace rename")
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(stage), os.fsencode(destination), 4)
    else:
        raise SafeZipError("this platform lacks atomic no-replace rename")
    if result:
        code = ctypes.get_errno() or errno.EIO
        raise OSError(code, os.strerror(code), str(destination))


def _operate(archive_path: str | os.PathLike[str],
             destination: str | os.PathLike[str] | None) -> dict:
    stage = None
    try:
        target = _destination(destination) if destination is not None else None
        with open(archive_path, "rb") as source:
            central_start, count = _preflight(source)
            with zipfile.ZipFile(source, "r") as archive:
                members = _members(source, archive, central_start, count)
                if target is not None:
                    stage = Path(tempfile.mkdtemp(prefix=".safezip-", dir=target.parent))
                manifest = _manifest(source, members, stage)
        if stage is not None:
            _commit(stage, target)
            stage = None
        return manifest
    except (OSError, ValueError, UnicodeError, EOFError, struct.error,
            zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error,
            NotImplementedError) as exc:
        raise SafeZipError(str(exc) or type(exc).__name__) from exc
    finally:
        if stage is not None:
            try:
                shutil.rmtree(stage)
            except OSError as exc:
                raise SafeZipError(f"could not remove staging directory: {exc}") from exc


def inspect_archive(archive_path: str | os.PathLike[str]) -> dict:
    """Validate every member and return its manifest without filesystem writes."""
    return _operate(archive_path, None)


def extract_archive(archive_path: str | os.PathLike[str],
                    destination: str | os.PathLike[str]) -> dict:
    """Extract into an absent destination, publishing only a complete result."""
    return _operate(archive_path, destination)
