"""Validate ZIP metadata and stream payloads without trusting declared sizes."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
from dataclasses import dataclass
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


class SafeZipError(ValueError):
    """An archive or destination cannot be processed safely."""


@dataclass(frozen=True)
class _Member:
    info: zipfile.ZipInfo
    path: str
    kind: str
    offset: int


def manifest_json(manifest: dict) -> str:
    """Return the exact canonical wire representation, including its newline."""
    return json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"


def _central_bounds(source: BinaryIO) -> tuple[int, int]:
    """Bound and count the central directory before ZipFile allocates its index."""
    source.seek(0, os.SEEK_END)
    length = source.tell()
    tail_size = min(length, 22 + 65535)
    source.seek(length - tail_size)
    tail = source.read(tail_size)
    index = len(tail)
    while True:
        index = tail.rfind(b"PK\x05\x06", 0, index)
        if index < 0:
            raise SafeZipError("missing or truncated ZIP end record")
        if index + 22 <= len(tail):
            end = struct.unpack_from("<4s4H2LH", tail, index)
            if index + 22 + end[7] == len(tail):
                break
    _, disk, central_disk, disk_count, count, size, offset, _ = end
    end_offset = length - tail_size + index
    directory_end = end_offset
    if end_offset >= 20:
        source.seek(end_offset - 20)
        locator = source.read(20)
        if locator[:4] == b"PK\x06\x07":
            _, zip64_disk, zip64_offset, disks = struct.unpack("<4sLQL", locator)
            if zip64_disk or disks != 1 or end_offset < 76:
                raise SafeZipError("invalid or multi-disk ZIP64 archive")
            directory_end = end_offset - 76
            source.seek(directory_end)
            record = source.read(56)
            values = struct.unpack("<4sQ2H2L4Q", record)
            if values[0] != b"PK\x06\x06" or values[1] != 44 or zip64_offset > directory_end:
                raise SafeZipError("invalid ZIP64 end record")
            disk, central_disk, disk_count, count, size, offset = values[4:]
    if disk or central_disk or disk_count != count:
        raise SafeZipError("multi-disk ZIP archives are unsupported")
    if count > MAX_ENTRIES:
        raise SafeZipError("archive exceeds 64 entries")
    if size == 0xFFFFFFFF or offset == 0xFFFFFFFF:
        raise SafeZipError("missing ZIP64 end record")
    start = directory_end - size
    if start < 0 or offset > start or size > count * (46 + 3 * 65535):
        raise SafeZipError("invalid central directory bounds")
    source.seek(start)
    for _ in range(count):
        header = source.read(46)
        if len(header) != 46 or header[:4] != b"PK\x01\x02":
            raise SafeZipError("invalid central directory entry")
        name_size, extra_size, comment_size = struct.unpack_from("<3H", header, 28)
        next_offset = source.tell() + name_size + extra_size + comment_size
        if next_offset > directory_end:
            raise SafeZipError("truncated central directory entry")
        source.seek(next_offset)
    if source.tell() != directory_end:
        raise SafeZipError("central directory entry count does not match")
    return start, count


def _portable_path(name: str) -> tuple[str, str]:
    directory = name.endswith("/")
    path = name[:-1] if directory else name
    components = path.split("/")
    for component in components:
        if (
            not _COMPONENT.fullmatch(component)
            or component in (".", "..")
            or component.endswith((".", " "))
            or component.split(".", 1)[0].rstrip(" ").upper() in _RESERVED
        ):
            raise SafeZipError(f"nonportable member name: {name!r}")
    return path, "dir" if directory else "file"


def _check_kind(info: zipfile.ZipInfo, kind: str) -> None:
    unix_type = stat.S_IFMT(info.external_attr >> 16)
    dos_directory = bool(info.external_attr & 0x10)
    directory = kind == "dir"
    if unix_type not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise SafeZipError(f"special-file member: {info.orig_filename!r}")
    if (
        (dos_directory and not directory)
        or (unix_type == 0 and dos_directory != directory)
        or (unix_type == stat.S_IFREG and directory)
        or (unix_type == stat.S_IFDIR and not directory)
    ):
        raise SafeZipError(f"inconsistent file/directory metadata: {info.orig_filename!r}")
    if directory and info.file_size != 0:
        raise SafeZipError("directory entries must have no payload")


def _local_offset(source: BinaryIO, info: zipfile.ZipInfo, central: int) -> int:
    if info.header_offset < 0 or info.header_offset + 30 > central:
        raise SafeZipError("invalid local header offset")
    source.seek(info.header_offset)
    header = source.read(30)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise SafeZipError("invalid local file header")
    fields = struct.unpack("<4s5H3L2H", header)
    flags, method = fields[2:4]
    crc, compressed, size, name_size, extra_size = fields[6:]
    if flags != info.flag_bits or method != info.compress_type:
        raise SafeZipError("local and central ZIP metadata disagree")
    name = source.read(name_size)
    extra = source.read(extra_size)
    if name != info.orig_filename.encode("ascii") or len(extra) != extra_size:
        raise SafeZipError("local and central member names disagree")
    if not flags & 8:
        if size == 0xFFFFFFFF or compressed == 0xFFFFFFFF:
            position = 0
            while position + 4 <= len(extra):
                tag, field_size = struct.unpack_from("<HH", extra, position)
                position += 4
                field = extra[position:position + field_size]
                if tag == 1:
                    if size == 0xFFFFFFFF:
                        if len(field) < 8:
                            raise SafeZipError("truncated ZIP64 local size")
                        size = struct.unpack_from("<Q", field)[0]
                        field = field[8:]
                    if compressed == 0xFFFFFFFF:
                        if len(field) < 8:
                            raise SafeZipError("truncated ZIP64 local compressed size")
                        compressed = struct.unpack_from("<Q", field)[0]
                    break
                position += field_size
        if (crc, compressed, size) != (info.CRC, info.compress_size, info.file_size):
            raise SafeZipError("local and central sizes or CRC disagree")
    offset = source.tell()
    if offset + info.compress_size > central:
        raise SafeZipError("member payload extends into the central directory")
    if flags & 8:
        if crc not in (0, info.CRC) or compressed not in (0, 0xFFFFFFFF, info.compress_size) or size not in (0, 0xFFFFFFFF, info.file_size):
            raise SafeZipError("inconsistent streaming local header")
        source.seek(offset + info.compress_size)
        descriptor = source.read(min(24, central - source.tell()))
        starts = (4, 0) if descriptor.startswith(b"PK\x07\x08") else (0,)
        expected = (info.CRC, info.compress_size, info.file_size)
        valid = any(
            len(descriptor) >= start + struct.calcsize(format)
            and struct.unpack_from(format, descriptor, start) == expected
            for start in starts for format in ("<LLL", "<LQQ")
        )
        if not valid:
            raise SafeZipError("invalid size or CRC in data descriptor")
    return offset


def _members(source: BinaryIO, archive: zipfile.ZipFile, central: int, count: int) -> list[_Member]:
    infos = archive.infolist()
    if len(infos) != count or len(infos) > MAX_ENTRIES:
        raise SafeZipError("invalid archive entry count")
    entries: dict[str, tuple[str, str]] = {}
    planned = []
    total = 0
    for info in infos:
        path, kind = _portable_path(info.orig_filename)
        folded = path.casefold()
        if folded in entries:
            raise SafeZipError(f"duplicate member or file/directory collision: {path!r}")
        entries[folded] = (path, kind)
        if info.flag_bits & ~0x080E:
            raise SafeZipError("encrypted or unsupported ZIP flags")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise SafeZipError("only stored and deflated members are supported")
        _check_kind(info, kind)
        if info.file_size > MAX_FILE_BYTES:
            raise SafeZipError("member exceeds 512 KiB")
        if info.file_size and (
            not info.compress_size or info.file_size > MAX_RATIO * info.compress_size
        ):
            raise SafeZipError("member exceeds compression ratio 100")
        if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
            raise SafeZipError("stored member sizes disagree")
        if kind == "file":
            total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise SafeZipError("archive exceeds 2 MiB of file data")
        planned.append((info, path, kind))
    for path, _ in entries.values():
        components = path.casefold().split("/")
        for index in range(1, len(components)):
            parent = entries.get("/".join(components[:index]))
            if parent is not None and parent[1] == "file":
                raise SafeZipError(f"file used as a parent directory: {parent[0]!r}")
    members = [
        _Member(info, path, kind, _local_offset(source, info, central))
        for info, path, kind in planned
    ]
    previous_end = 0
    for member in sorted(members, key=lambda item: item.info.header_offset):
        if member.info.header_offset < previous_end:
            raise SafeZipError("overlapping ZIP members")
        previous_end = member.offset + member.info.compress_size
    return sorted(members, key=lambda item: item.path)


def _stream(source: BinaryIO, member: _Member, sink: BinaryIO | None) -> tuple[int, str]:
    info = member.info
    source.seek(member.offset)
    remaining = info.compress_size
    size = 0
    crc = 0
    digest = hashlib.sha256()
    decoder = zlib.decompressobj(-zlib.MAX_WBITS) if info.compress_type == 8 else None

    def consume(data: bytes) -> None:
        nonlocal size, crc
        size += len(data)
        if size > info.file_size or size > MAX_FILE_BYTES:
            raise SafeZipError("actual member size exceeds its declared size or quota")
        crc = zlib.crc32(data, crc)
        digest.update(data)
        if sink is not None:
            sink.write(data)

    while remaining:
        block = source.read(min(CHUNK_BYTES, remaining))
        if not block:
            raise SafeZipError("truncated member payload")
        remaining -= len(block)
        if decoder is None:
            consume(block)
            continue
        pending = block
        while True:
            limit = min(CHUNK_BYTES, info.file_size - size + 1)
            data = decoder.decompress(pending, limit)
            pending = decoder.unconsumed_tail
            consume(data)
            if decoder.unused_data or (decoder.eof and remaining):
                raise SafeZipError("trailing bytes after deflate stream")
            if pending or (len(data) == limit and not decoder.eof):
                continue
            break
    if decoder is not None and not decoder.eof:
        raise SafeZipError("incomplete deflate stream")
    if size != info.file_size or crc != info.CRC:
        raise SafeZipError(f"size or CRC mismatch: {member.path!r}")
    return size, digest.hexdigest()


def _manifest(source: BinaryIO, members: list[_Member], staging: Path | None) -> dict:
    entries = []
    total = 0
    file_count = 0
    for member in members:
        target = staging.joinpath(*member.path.split("/")) if staging else None
        if member.kind == "dir":
            _stream(source, member, None)
            if target is not None:
                target.mkdir(parents=True, exist_ok=True)
            size, digest = 0, None
        else:
            if target is None:
                size, digest = _stream(source, member, None)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as sink:
                    size, digest = _stream(source, member, sink)
            total += size
            file_count += 1
            if total > MAX_TOTAL_BYTES:
                raise SafeZipError("actual total exceeds 2 MiB")
        entries.append({"path": member.path, "kind": member.kind, "size": size, "sha256": digest})
    return {"schema": 1, "entries": entries, "file_count": file_count,
            "total_uncompressed_bytes": total}


def _destination(destination: os.PathLike | str) -> Path:
    path = Path(os.path.abspath(destination))
    if os.path.lexists(path):
        raise SafeZipError("destination already exists")
    parent = path.parent
    if not parent.is_dir():
        raise SafeZipError("destination parent must be an existing directory")
    if parent.is_symlink() or os.path.isjunction(parent):
        raise SafeZipError("destination parent must not be a link or junction")
    return path


def _commit(staging: Path, destination: Path) -> None:
    """Publish an entire directory, with an atomic no-replace platform primitive."""
    if os.path.lexists(destination):
        raise SafeZipError("destination already exists")
    if os.name == "nt":
        os.rename(staging, destination)  # Windows rename never replaces a destination.
        return
    library = ctypes.CDLL(None, use_errno=True)
    if hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        arguments = (-100, os.fsencode(staging), -100, os.fsencode(destination), 1)
    elif hasattr(library, "renamex_np"):
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        arguments = (os.fsencode(staging), os.fsencode(destination), 4)
    else:
        raise SafeZipError("this platform lacks atomic directory rename without replacement")
    rename.restype = ctypes.c_int
    if rename(*arguments) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), os.fspath(destination))


def _process(archive_path: os.PathLike | str, destination: Path | None) -> dict:
    staging = None
    try:
        if not stat.S_ISREG(os.stat(archive_path).st_mode):
            raise SafeZipError("archive must be a regular file")
        with open(archive_path, "rb") as source:
            central, count = _central_bounds(source)
            with zipfile.ZipFile(source, "r") as archive:
                members = _members(source, archive, central, count)
                if destination is not None:
                    staging = Path(tempfile.mkdtemp(prefix=".safezip-", dir=destination.parent))
                manifest = _manifest(source, members, staging)
        if staging is not None:
            _commit(staging, destination)
            staging = None
        return manifest
    finally:
        if staging is not None:
            shutil.rmtree(staging)


def inspect_archive(archive_path: os.PathLike | str) -> dict:
    """Read and validate the entire archive, returning its canonical manifest."""
    return _process(archive_path, None)


def extract_archive(archive_path: os.PathLike | str, destination: os.PathLike | str) -> dict:
    """Extract into a fresh destination; failures remove private staging data."""
    return _process(archive_path, _destination(destination))
