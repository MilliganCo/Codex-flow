"""Validate ZIP metadata and bounded payloads before publishing any files."""

import argparse
import binascii
import ctypes
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
import zipfile
import zlib


MAX_ENTRIES = 64
MAX_FILE = 512 * 1024
MAX_TOTAL = 2 * 1024 * 1024
MAX_RATIO = 100
CHUNK = 64 * 1024
COMPONENT = re.compile(r"[A-Za-z0-9._ -]{1,80}\Z", re.ASCII)
RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}


class InvalidArchive(ValueError):
    """An archive or destination does not satisfy the SafeZip contract."""


def _require(condition, message):
    if not condition:
        raise InvalidArchive(message)


def _directory_bounds(stream):
    """Bound the central-directory allocation before ZipFile parses it.

    Small ZIP64 archives are supported. ZIP64 offsets need no large allocation.
    Multipart archives and trailing bytes after the ZIP comment are rejected.
    """
    stream.seek(0, os.SEEK_END)
    length = stream.tell()
    stream.seek(max(0, length - 65557))
    tail = stream.read(65557)
    position = len(tail)
    while True:
        position = tail.rfind(b"PK\x05\x06", 0, position)
        _require(position >= 0, "missing ZIP end record")
        if position + 22 <= len(tail):
            end = struct.unpack_from("<4s4H2LH", tail, position)
            if position + 22 + end[7] == len(tail):
                break
    end_offset = length - len(tail) + position
    _, disk, cd_disk, on_disk, count, cd_size, cd_offset, _ = end
    _require(disk == cd_disk == 0 and on_disk == count, "multipart ZIP is unsupported")
    cd_end = end_offset
    if end_offset >= 20:
        stream.seek(end_offset - 20)
        locator = stream.read(20)
        if locator[:4] == b"PK\x06\x07":
            _, zip_disk, zip_offset, disks = struct.unpack("<4sLQL", locator)
            _require(zip_disk == 0 and disks == 1, "multipart ZIP64 is unsupported")
            _require(zip_offset + 56 <= end_offset - 20, "invalid ZIP64 offset")
            stream.seek(zip_offset)
            record = stream.read(56)
            _require(len(record) == 56, "truncated ZIP64 end record")
            fields = struct.unpack("<4sQ2H2L4Q", record)
            _require(fields[0] == b"PK\x06\x06" and fields[1] >= 44,
                     "invalid ZIP64 end record")
            _require(zip_offset + 12 + fields[1] == end_offset - 20,
                     "invalid ZIP64 record length")
            _require(fields[4] == fields[5] == 0 and fields[6] == fields[7],
                     "multipart ZIP64 is unsupported")
            count, cd_size, cd_offset = fields[7:10]
            cd_end = zip_offset
    _require(count <= MAX_ENTRIES, "more than 64 entries")
    # Every central entry has three uint16 length fields; no other large
    # allocation is necessary for a supported archive with <=64 entries.
    _require(cd_size <= count * (46 + 3 * 65535), "oversized central directory")
    _require(cd_offset + cd_size == cd_end, "invalid central directory bounds")
    return count, cd_offset


def _canonical(info):
    name = info.orig_filename
    _require(name == info.filename, "member name was truncated or rewritten")
    is_dir = name.endswith("/")
    path = name[:-1] if is_dir else name
    for component in path.split("/"):
        _require(COMPONENT.fullmatch(component) is not None,
                 "member name has an invalid component")
        _require(component not in (".", "..") and not component.endswith((".", " ")),
                 "dot components and trailing dots/spaces are forbidden")
        _require(component.split(".", 1)[0].rstrip(" ").lower() not in RESERVED,
                 "reserved device name")
    dos_dir = bool(info.external_attr & 0x10)
    _require(dos_dir == is_dir, "directory flag and member name disagree")
    file_type = stat.S_IFMT(info.external_attr >> 16)
    _require(file_type in (0, stat.S_IFREG, stat.S_IFDIR),
             "symlinks and special files are forbidden")
    _require(file_type == 0 or (file_type == stat.S_IFDIR) == is_dir,
             "Unix file type and member name disagree")
    return path, is_dir


def _metadata(infos):
    _require(len(infos) <= MAX_ENTRIES, "more than 64 entries")
    members = []
    paths = {}
    total = 0
    for info in infos:
        path, is_dir = _canonical(info)
        key = path.lower()
        _require(key not in paths, "case-insensitive duplicate or file/directory collision")
        paths[key] = is_dir
        _require(not (info.flag_bits & ~0x080E), "encrypted or unsupported ZIP flags")
        _require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                 "only stored and deflated members are supported")
        _require(info.file_size >= 0 and info.compress_size >= 0, "negative member size")
        if is_dir:
            _require(info.file_size == 0, "directory contains a payload")
        else:
            _require(info.file_size <= MAX_FILE, "file exceeds 512 KiB")
            total += info.file_size
            _require(total <= MAX_TOTAL, "file total exceeds 2 MiB")
            _require(info.file_size == 0 or info.compress_size > 0,
                     "positive file size with zero compressed size")
            _require(info.file_size <= MAX_RATIO * info.compress_size,
                     "compression ratio exceeds 100")
        members.append((info, path, is_dir))
    for key in paths:
        parts = key.split("/")
        for index in range(1, len(parts)):
            _require(paths.get("/".join(parts[:index]), True),
                     "a file is used as a parent directory")
    return members


def _local_sizes(extra, size, compressed):
    """Read only the ZIP64 size values needed by a local header."""
    if size != 0xFFFFFFFF and compressed != 0xFFFFFFFF:
        return size, compressed
    offset = 0
    while offset + 4 <= len(extra):
        tag, length = struct.unpack_from("<HH", extra, offset)
        offset += 4
        _require(offset + length <= len(extra), "truncated local extra field")
        if tag == 1:
            end = offset + length
            values = []
            for value in (size, compressed):
                if value == 0xFFFFFFFF:
                    _require(offset + 8 <= end, "missing ZIP64 size")
                    value = struct.unpack_from("<Q", extra, offset)[0]
                    offset += 8
                values.append(value)
            return tuple(values)
        offset += length
    raise InvalidArchive("missing ZIP64 local extra field")


def _local_headers(stream, members, central_start):
    spans = []
    offsets = {}
    for info, path, _ in members:
        _require(0 <= info.header_offset < central_start, "invalid local header offset")
        stream.seek(info.header_offset)
        data = stream.read(30)
        _require(len(data) == 30, "truncated local header")
        signature, version, flags, method, _, _, crc, compressed, size, nlen, xlen = (
            struct.unpack("<4s5H3L2H", data))
        _require(signature == b"PK\x03\x04", "invalid local header signature")
        _require(flags == info.flag_bits and method == info.compress_type,
                 "local and central ZIP flags/method disagree")
        raw_name = stream.read(nlen)
        extra = stream.read(xlen)
        _require(len(raw_name) == nlen and len(extra) == xlen, "truncated local header")
        name = raw_name.decode("utf-8" if flags & 0x800 else "cp437")
        _require(name == info.orig_filename, "local and central names disagree")
        if not flags & 8:
            size, compressed = _local_sizes(extra, size, compressed)
            _require((size, compressed, crc) == (info.file_size, info.compress_size, info.CRC),
                     "local and central sizes/CRC disagree")
        start = stream.tell()
        end = start + info.compress_size
        _require(end <= central_start, "member data overlaps the central directory")
        spans.append((info.header_offset, end))
        offsets[path] = start
    spans.sort()
    _require(all(left[1] <= right[0] for left, right in zip(spans, spans[1:])),
             "overlapping ZIP members")
    return offsets


def _payload(stream, info, start, limit, keep):
    """Decode with an output bound independent of the declared file size.

    ZipExtFile deliberately stops at the declared size. Reading raw deflate
    here also detects a forged small size hiding a much larger payload.
    """
    stream.seek(start)
    remaining = info.compress_size
    decoder = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
    size = crc = 0
    digest = hashlib.sha256()
    contents = bytearray() if keep else None

    def consume(block):
        nonlocal size, crc
        size += len(block)
        _require(size <= limit, "actual decompressed bytes exceed quota")
        digest.update(block)
        crc = binascii.crc32(block, crc)
        if keep:
            contents.extend(block)

    while remaining:
        block = stream.read(min(CHUNK, remaining))
        _require(bool(block), "truncated member data")
        remaining -= len(block)
        if decoder is None:
            consume(block)
        else:
            while block:
                decoded = decoder.decompress(block, min(CHUNK, limit - size + 1))
                consume(decoded)
                _require(not decoder.unused_data, "trailing compressed member data")
                block = decoder.unconsumed_tail
            _require(not decoder.eof or remaining == 0, "trailing compressed member data")
    if decoder is not None:
        _require(decoder.eof, "truncated deflate stream")
    _require(size == info.file_size, "actual size differs from ZIP metadata")
    _require(crc & 0xFFFFFFFF == info.CRC, "damaged member CRC")
    return size, digest.hexdigest(), bytes(contents) if keep else None


def validate(archive_path, keep=False):
    entries = []
    payloads = {}
    total = file_count = 0
    with open(archive_path, "rb") as stream:
        count, central_start = _directory_bounds(stream)
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            _require(len(infos) == count, "central directory entry count disagrees")
            members = _metadata(infos)
            offsets = _local_headers(stream, members, central_start)
            for info, path, is_dir in members:
                limit = 0 if is_dir else min(MAX_FILE, MAX_TOTAL - total)
                size, digest, payload = _payload(stream, info, offsets[path], limit, keep)
                entries.append({"path": path, "kind": "dir" if is_dir else "file",
                                "size": size, "sha256": None if is_dir else digest})
                if not is_dir:
                    total += size
                    file_count += 1
                    if keep:
                        payloads[path] = payload
    entries.sort(key=lambda entry: entry["path"])
    return {"schema": 1, "entries": entries, "file_count": file_count,
            "total_uncompressed_bytes": total}, payloads


def _rename_absent(source, destination):
    """Publish a directory atomically without replacing even an empty directory."""
    if os.name == "nt":
        os.rename(source, destination)  # Windows rename always refuses an existing target.
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                           ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(destination), 4)
    else:
        raise InvalidArchive("atomic no-replace directory rename is unavailable on this platform")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def extract(archive_path, destination):
    target = Path(os.path.abspath(destination))
    _require(not os.path.lexists(target), "destination already exists")
    parent = target.parent.resolve(strict=True)
    _require(parent.is_dir(), "destination parent must be an existing directory")
    target = parent / target.name
    _require(not os.path.lexists(target), "destination already exists")
    manifest, payloads = validate(archive_path, keep=True)
    stage = None
    try:
        _require(not os.path.lexists(target), "destination already exists")
        stage = Path(tempfile.mkdtemp(prefix=".safezip-", dir=parent))
        for entry in manifest["entries"]:
            path = stage.joinpath(*entry["path"].split("/"))
            if entry["kind"] == "dir":
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    output.write(payloads[entry["path"]])
        _rename_absent(stage, target)
        stage = None
    finally:
        if stage is not None:
            shutil.rmtree(stage)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="safezip", description="Inspect or atomically extract a bounded, portable ZIP offline.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect", help="validate and print a canonical JSON manifest")
    inspect_parser.add_argument("archive", help="stored/deflated ZIP archive")
    extract_parser = commands.add_parser("extract", help="validate and extract into an absent directory")
    extract_parser.add_argument("archive", help="stored/deflated ZIP archive")
    extract_parser.add_argument("--dest", required=True, help="absent destination; parent must exist")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "inspect":
            manifest, _ = validate(arguments.archive)
        else:
            manifest = extract(arguments.archive, arguments.dest)
        encoded = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")) + "\n").encode("utf-8")
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return 0
    except (OSError, ValueError, EOFError, RuntimeError, zipfile.BadZipFile,
            zipfile.LargeZipFile, struct.error, zlib.error) as error:
        print(f"safezip: {error}", file=sys.stderr)
        return 1
