"""Validation, bounded streaming, and no-replace directory publication.

ZIP metadata is untrusted. Index bounds and every member's metadata/local header
are checked before payload processing. Raw deflate is read with a maximum output
length: ZipExtFile alone can hide output beyond a forged uncompressed size.
"""

import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import zipfile
import zlib
from dataclasses import dataclass


MAX_ENTRIES = 64
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_RATIO = 100
CHUNK_BYTES = 64 * 1024
_COMPONENT = re.compile(r"[A-Za-z0-9._ -]{1,80}\Z", re.ASCII)
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_END = struct.Struct("<4s4H2IH")
_CENTRAL = struct.Struct("<4s6H3I5H2I")
_LOCAL = struct.Struct("<4s5H3I2H")
_ENCRYPTED = 0x0001 | 0x0040 | 0x2000


class SafeZipError(Exception):
    """An invalid archive or an extraction that cannot be completed safely."""


@dataclass(frozen=True)
class _Member:
    info: zipfile.ZipInfo
    path: str
    kind: str
    offset: int


def manifest_bytes(manifest):
    """Return exactly the v1 canonical UTF-8 JSON representation, including LF."""
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _read_exact(source, count):
    data = source.read(count)
    if len(data) != count:
        raise SafeZipError("truncated ZIP archive")
    return data


def _preflight_index(source):
    """Bound the index before ZipFile can allocate its central directory.

    Permit ordinary ZIP and the fixed ZIP64 end records supported by zipfile.
    A prepended stub is harmless; member offsets are adjusted by zipfile.
    """
    source.seek(0, os.SEEK_END)
    length = source.tell()
    tail_length = min(length, _END.size + 65535)
    source.seek(length - tail_length)
    tail = source.read(tail_length)
    marker = tail.rfind(b"PK\x05\x06")
    if marker < 0 or len(tail) - marker < _END.size:
        raise SafeZipError("missing ZIP end record")
    end = _END.unpack_from(tail, marker)
    if marker + _END.size + end[7] != len(tail):
        raise SafeZipError("invalid ZIP comment length or trailing data")
    end_offset = length - tail_length + marker
    _, disk, index_disk, disk_count, count, index_size, index_offset, _ = end
    index_end = end_offset

    # ZIP64's locator is immediately before the ordinary end record.
    if end_offset >= 20:
        source.seek(end_offset - 20)
        locator = _read_exact(source, 20)
        if locator[:4] == b"PK\x06\x07":
            _, locator_disk, record_offset, disks = struct.unpack("<4sIQI", locator)
            if locator_disk or disks != 1 or end_offset < 76:
                raise SafeZipError("multi-disk or invalid ZIP64 archive")
            index_end = end_offset - 76
            source.seek(index_end)
            record = struct.unpack("<4sQ2H2I4Q", _read_exact(source, 56))
            if record[0] != b"PK\x06\x06" or record[1] != 44 or record_offset > index_end:
                raise SafeZipError("invalid or unsupported ZIP64 end record")
            _, _, _, _, disk, index_disk, disk_count, count, index_size, index_offset = record
    if disk or index_disk or disk_count != count:
        raise SafeZipError("multi-disk ZIP archives are not supported")
    if count > MAX_ENTRIES:
        raise SafeZipError("archive exceeds the 64-entry limit")
    # Each central record has three unsigned 16-bit variable field lengths.
    if index_size > count * (_CENTRAL.size + 3 * 65535):
        raise SafeZipError("invalid or oversized ZIP index")
    index_start = index_end - index_size
    if index_start < 0 or index_offset > index_start:
        raise SafeZipError("invalid ZIP index offset")
    source.seek(index_start)
    for _ in range(count):
        if source.tell() + _CENTRAL.size > index_end:
            raise SafeZipError("truncated ZIP index")
        header = _CENTRAL.unpack(_read_exact(source, _CENTRAL.size))
        if header[0] != b"PK\x01\x02" or header[13] != 0:
            raise SafeZipError("invalid or multi-disk ZIP index")
        next_offset = source.tell() + sum(header[10:13])
        if next_offset > index_end:
            raise SafeZipError("invalid ZIP index field lengths")
        source.seek(next_offset)
    if source.tell() != index_end:
        raise SafeZipError("ZIP index entry count does not match its contents")
    return index_start, count


def _member_path(info):
    # orig_filename retains NULs/backslashes which ZipInfo may normalize away.
    name = info.orig_filename
    is_directory = name.endswith("/")
    path = name[:-1] if is_directory else name
    for component in path.split("/"):
        if (not _COMPONENT.fullmatch(component) or component in (".", "..")
                or component.endswith((".", " "))):
            raise SafeZipError(f"non-portable member name: {name!r}")
        if component.split(".", 1)[0].rstrip(" ").upper() in _RESERVED:
            raise SafeZipError(f"reserved member name: {name!r}")
    if info.filename != name:
        raise SafeZipError(f"normalized or truncated member name: {name!r}")

    dos_directory = bool(info.external_attr & 0x10)
    file_type = stat.S_IFMT(info.external_attr >> 16)
    if file_type == 0:
        if dos_directory != is_directory:
            raise SafeZipError(f"directory flag/name mismatch: {name!r}")
    elif file_type == stat.S_IFREG:
        if is_directory or dos_directory:
            raise SafeZipError(f"regular-file type/name mismatch: {name!r}")
    elif file_type == stat.S_IFDIR:
        if not is_directory:
            raise SafeZipError(f"directory type/name mismatch: {name!r}")
    else:
        raise SafeZipError(f"symlink or special-file entry: {name!r}")
    return path, "dir" if is_directory else "file"


def _plan_members(source, archive, index_start, count):
    infos = archive.infolist()
    if len(infos) != count or archive.start_dir != index_start:
        raise SafeZipError("inconsistent ZIP index")
    paths = {}
    metadata = []
    total = 0
    for info in infos:
        path, kind = _member_path(info)
        if info.flag_bits & _ENCRYPTED:
            raise SafeZipError(f"encrypted member: {path!r}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise SafeZipError(f"unsupported compression: {path!r}")
        if info.file_size < 0 or info.compress_size < 0:
            raise SafeZipError("negative ZIP size")
        if kind == "dir" and info.file_size != 0:
            raise SafeZipError(f"directory has a payload: {path!r}")
        if info.file_size > MAX_FILE_BYTES:
            raise SafeZipError("member exceeds the 512 KiB limit")
        if info.file_size and (not info.compress_size
                               or info.file_size > MAX_RATIO * info.compress_size):
            raise SafeZipError("member exceeds the compression ratio limit of 100")
        if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
            raise SafeZipError("stored member has inconsistent sizes")
        if kind == "file":
            total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise SafeZipError("archive exceeds the 2 MiB uncompressed limit")

        folded = path.lower()
        # At most 64 paths: compare whole paths without allocating every implied
        # prefix (a ZIP name itself may be up to 65535 bytes deep).
        for previous, previous_kind in paths.items():
            if folded == previous:
                raise SafeZipError(f"duplicate or colliding member: {path!r}")
            if ((previous_kind == "file" and folded.startswith(previous + "/"))
                    or (kind == "file" and previous.startswith(folded + "/"))):
                raise SafeZipError(f"file used as a parent directory: {path!r}")
        paths[folded] = kind
        metadata.append((info, path, kind))

    # Validate every local header before reading any compressed payload.
    members = []
    spans = []
    for info, path, kind in metadata:
        if info.header_offset < 0 or info.header_offset + _LOCAL.size > index_start:
            raise SafeZipError("invalid member header offset")
        source.seek(info.header_offset)
        header = _LOCAL.unpack(_read_exact(source, _LOCAL.size))
        signature, _, flags, method, _, _, crc, compressed, size, name_len, extra_len = header
        if signature != b"PK\x03\x04" or flags != info.flag_bits or method != info.compress_type:
            raise SafeZipError(f"local header mismatch: {path!r}")
        if flags & _ENCRYPTED:
            raise SafeZipError(f"encrypted local header: {path!r}")
        data_start = info.header_offset + _LOCAL.size + name_len + extra_len
        data_end = data_start + info.compress_size
        if data_end > index_start:
            raise SafeZipError("member data overlaps the ZIP index")
        raw_name = _read_exact(source, name_len)
        encoding = "utf-8" if flags & 0x800 else "cp437"
        if raw_name.decode(encoding) != info.orig_filename:
            raise SafeZipError(f"local/central member names differ: {path!r}")
        if not flags & 0x08:
            if (crc != info.CRC or compressed not in (info.compress_size, 0xFFFFFFFF)
                    or size not in (info.file_size, 0xFFFFFFFF)):
                raise SafeZipError(f"local/central sizes or CRC differ: {path!r}")
        spans.append((info.header_offset, data_end))
        members.append(_Member(info, path, kind, data_start))
    previous_end = 0
    for start, end in sorted(spans):
        if start < previous_end:
            raise SafeZipError("overlapping ZIP members")
        previous_end = end
    return sorted(members, key=lambda member: member.path)


def _read_member(source, member, sink, total_so_far):
    info = member.info
    limit = min(info.file_size, MAX_FILE_BYTES, MAX_TOTAL_BYTES - total_so_far)
    source.seek(member.offset)
    digest = hashlib.sha256()
    size = 0
    crc = 0

    def consume(data):
        nonlocal size, crc
        size += len(data)
        if size > limit:
            raise SafeZipError(f"actual output exceeds declared size or quota: {member.path!r}")
        if size and size > MAX_RATIO * info.compress_size:
            raise SafeZipError("actual output exceeds the compression ratio limit")
        crc = binascii.crc32(data, crc)
        digest.update(data)
        if sink is not None:
            sink.write(data)

    remaining = info.compress_size
    if info.compress_type == zipfile.ZIP_STORED:
        while remaining:
            data = _read_exact(source, min(CHUNK_BYTES, remaining))
            remaining -= len(data)
            consume(data)
    else:
        decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        pending = b""
        while True:
            if not pending and remaining:
                pending = _read_exact(source, min(CHUNK_BYTES, remaining))
                remaining -= len(pending)
            data = decoder.decompress(pending, min(CHUNK_BYTES, limit - size + 1))
            pending = decoder.unconsumed_tail
            consume(data)
            if decoder.eof:
                if decoder.unused_data or pending or remaining:
                    raise SafeZipError(f"trailing compressed member data: {member.path!r}")
                break
            if not pending and not remaining and not data:
                raise SafeZipError(f"truncated deflate stream: {member.path!r}")
    if size != info.file_size or crc != info.CRC:
        raise SafeZipError(f"size or CRC mismatch: {member.path!r}")
    return size, digest.hexdigest()


def _mkdir_chain(staging, components):
    # Iterative mkdir avoids recursion limits on deeply nested member names.
    current = staging
    for component in components:
        current = current / component
        current.mkdir(exist_ok=True)


def _remove_staging(staging):
    # The private tree contains only our files/directories. Still avoid following
    # symlinks and avoid recursive cleanup for deeply nested valid components.
    current = staging
    while True:
        descendant = None
        with os.scandir(current) as children:
            for child in children:
                if child.is_dir(follow_symlinks=False):
                    descendant = Path(child.path)
                    break
                else:
                    os.unlink(child.path)
        if descendant is not None:
            current = descendant
            continue
        current.rmdir()
        if current == staging:
            return
        current = current.parent


def _read_all(source, members, staging):
    entries = []
    total = 0
    file_count = 0
    for member in members:
        sink_path = None if staging is None else staging.joinpath(*member.path.split("/"))
        if member.kind == "dir":
            _read_member(source, member, None, total)
            if sink_path is not None:
                _mkdir_chain(staging, member.path.split("/"))
            size, digest = 0, None
        else:
            if sink_path is None:
                size, digest = _read_member(source, member, None, total)
            else:
                _mkdir_chain(staging, member.path.split("/")[:-1])
                with sink_path.open("xb") as sink:
                    size, digest = _read_member(source, member, sink, total)
            total += size
            file_count += 1
        entries.append({"path": member.path, "kind": member.kind, "size": size, "sha256": digest})
    return {"schema": 1, "entries": entries, "file_count": file_count,
            "total_uncompressed_bytes": total}


def _destination_path(destination):
    path = Path(os.path.abspath(os.fspath(destination)))
    if os.path.lexists(path):
        raise SafeZipError("destination already exists")
    if not path.parent.is_dir():
        raise SafeZipError("destination parent must be an existing directory")
    return path


def _commit_directory(staging, destination):
    """Atomically publish a complete directory, refusing even a racing arrival.

    os.rename is no-replace on Windows. POSIX rename can replace empty directories,
    so use the OS's exclusive-rename primitive through standard-library ctypes.
    Fail closed when a platform/filesystem cannot provide that guarantee.
    """
    if os.path.lexists(destination):
        raise SafeZipError("destination already exists")
    if os.name == "nt":
        os.rename(staging, destination)
        return

    import ctypes

    library = ctypes.CDLL(None, use_errno=True)
    source_bytes, destination_bytes = os.fsencode(staging), os.fsencode(destination)
    if sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                           ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, source_bytes, -100, destination_bytes, 1)  # RENAME_NOREPLACE
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source_bytes, destination_bytes, 4)  # RENAME_EXCL
    else:
        raise SafeZipError("this platform lacks an atomic no-replace directory rename")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def _process_archive(archive_path, destination):
    staging = None
    try:
        destination = None if destination is None else _destination_path(destination)
        with open(archive_path, "rb") as source:
            index_start, count = _preflight_index(source)
            with zipfile.ZipFile(source, "r") as archive:
                members = _plan_members(source, archive, index_start, count)
                if destination is not None:
                    staging = Path(tempfile.mkdtemp(prefix=".safezip-", dir=destination.parent))
                manifest = _read_all(source, members, staging)
        if destination is not None:
            _commit_directory(staging, destination)
            staging = None
        return manifest
    except SafeZipError:
        raise
    except (OSError, ValueError, EOFError, RuntimeError, OverflowError,
            zipfile.BadZipFile, zipfile.LargeZipFile,
            struct.error, zlib.error) as exc:
        raise SafeZipError(str(exc)) from None
    finally:
        if staging is not None:
            _remove_staging(staging)


def inspect_archive(archive_path):
    """Validate all metadata and bytes, returning a manifest without filesystem writes."""
    return _process_archive(archive_path, None)


def extract_archive(archive_path, destination):
    """Validate into private sibling staging, then exclusively publish destination."""
    return _process_archive(archive_path, destination)
