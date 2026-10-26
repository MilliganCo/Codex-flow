"""Offline regression tests. All temporary data stays under this workspace."""

import binascii
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import shlex
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile
import zlib

from safezip import SafeZipError, extract_archive, inspect_archive, manifest_bytes
from safezip import core


ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / ".tmp"


def make_zip(entries, compression=zipfile.ZIP_STORED, timestamp=(2024, 1, 2, 3, 4, 6)):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        for name, payload in entries:
            if isinstance(name, zipfile.ZipInfo):
                info = name
            else:
                info = zipfile.ZipInfo(name, timestamp)
                info.create_system = 3
                info.external_attr = ((stat.S_IFDIR | 0o755) << 16 | 0x10
                                      if name.endswith("/") else (stat.S_IFREG | 0o644) << 16)
            info.compress_type = compression
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(info, payload)
    return stream.getvalue()


def raw_zip(name, raw, size, crc, method=zipfile.ZIP_DEFLATED, flags=0, attr=None):
    """Build a single-entry ZIP with caller-specified (possibly forged) metadata."""
    name = name.encode("ascii")
    if attr is None:
        attr = (stat.S_IFREG | 0o600) << 16
    local = struct.pack("<4s5H3I2H", b"PK\x03\x04", 20, flags, method, 0, 0,
                        crc, len(raw), size, len(name), 0) + name + raw
    central = struct.pack("<4s6H3I5H2I", b"PK\x01\x02", (3 << 8) | 20, 20,
                          flags, method, 0, 0, crc, len(raw), size, len(name),
                          0, 0, 0, 0, attr, 0) + name
    end = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 1, 1,
                      len(central), len(local), 0)
    return local + central + end


def raw_deflate(data):
    encoder = zlib.compressobj(wbits=-15)
    return encoder.compress(data) + encoder.flush()


class SafeZipTests(unittest.TestCase):
    def setUp(self):
        TEMP_ROOT.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-", dir=TEMP_ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "input archive.zip"
        self.destination = self.root / "new destination"

    def write_zip(self, entries, **kwargs):
        data = make_zip(entries, **kwargs)
        self.archive.write_bytes(data)
        return data

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "safezip", *map(str, arguments)],
                              cwd=ROOT, capture_output=True, timeout=20)

    def assert_clean_failure(self, data):
        self.archive.write_bytes(data)
        before = set(self.root.iterdir())
        for operation in (lambda: inspect_archive(self.archive),
                          lambda: extract_archive(self.archive, self.destination)):
            with self.assertRaises(SafeZipError):
                operation()
            self.assertFalse(os.path.lexists(self.destination))
            self.assertEqual(set(self.root.iterdir()), before)
            self.assertEqual(self.archive.read_bytes(), data)

    def test_valid_manifest_and_byte_exact_extraction(self):
        binary = bytes(range(256)) * 8
        original = self.write_zip([("z.bin", binary), ("folder/", b""),
                                   ("folder/empty", b""), ("folder/a.txt", b"hello\r\n")])
        expected = {"schema": 1, "entries": [
            {"path": "folder", "kind": "dir", "size": 0, "sha256": None},
            {"path": "folder/a.txt", "kind": "file", "size": 7,
             "sha256": hashlib.sha256(b"hello\r\n").hexdigest()},
            {"path": "folder/empty", "kind": "file", "size": 0,
             "sha256": hashlib.sha256(b"").hexdigest()},
            {"path": "z.bin", "kind": "file", "size": len(binary),
             "sha256": hashlib.sha256(binary).hexdigest()}],
            "file_count": 3, "total_uncompressed_bytes": len(binary) + 7}
        before = set(self.root.iterdir())
        self.assertEqual(inspect_archive(self.archive), expected)
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertEqual(extract_archive(self.archive, self.destination), expected)
        self.assertEqual((self.destination / "z.bin").read_bytes(), binary)
        self.assertEqual((self.destination / "folder/a.txt").read_bytes(), b"hello\r\n")
        self.assertEqual((self.destination / "folder/empty").read_bytes(), b"")
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".safezip-*")))

    def test_cli_commands_agree_on_exact_json_bytes_and_space_paths(self):
        self.write_zip([("a file.txt", b"a\x00b\xff"), ("d/", b"")],
                       compression=zipfile.ZIP_DEFLATED)
        expected = (json.dumps(inspect_archive(self.archive), ensure_ascii=False,
                               sort_keys=True, separators=(",", ":")) + "\n").encode()
        inspected = self.cli("inspect", self.archive)
        extracted = self.cli("extract", self.archive, "--dest", self.destination)
        for result in (inspected, extracted):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            self.assertEqual(result.stdout, expected)
            self.assertNotIn(b"\r\n", result.stdout)

    def test_empty_archive(self):
        self.write_zip([])
        expected = {"schema": 1, "entries": [], "file_count": 0, "total_uncompressed_bytes": 0}
        self.assertEqual(inspect_archive(self.archive), expected)
        self.assertEqual(extract_archive(self.archive, self.destination), expected)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_order_and_timestamp_determinism(self):
        entries = [("b/", b""), ("b/c", b"abcd"), ("A", b"\x00\xff")]
        self.write_zip(entries, compression=zipfile.ZIP_STORED)
        first = manifest_bytes(inspect_archive(self.archive))
        self.write_zip(list(reversed(entries)), compression=zipfile.ZIP_DEFLATED,
                       timestamp=(2031, 6, 7, 8, 9, 10))
        self.assertEqual(manifest_bytes(inspect_archive(self.archive)), first)

    def test_all_allowed_component_characters_and_length_boundary(self):
        name = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._ -x"
        self.write_zip([(name, b"1"), ("x" * 80, b"2"), ("COM10.txt", b"3"),
                        ("COM0", b"4"), ("directory with spaces/file-name_2.ext", b"5")])
        self.assertEqual(inspect_archive(self.archive)["file_count"], 5)

    def test_reject_nonportable_and_traversal_names(self):
        names = ["/abs", "C:/drive", "C:drive", "//server/share", "\\\\server\\share",
                 "back\\slash", "a:b", "a\x00hidden", "caf\u00e9", "a\tb", "a\nb",
                 "bad*name", "bad?name", "x" * 81, "a.", "a ", ".", "..", "./a",
                 "../a", "a/./b", "a/../b", "a//b", "a//", "/", "a///b"]
        for name in names:
            with self.subTest(name=name):
                if "\x00" in name or "\\" in name:
                    data = raw_zip(name, b"x", 1, binascii.crc32(b"x"), zipfile.ZIP_STORED)
                else:
                    data = make_zip([(name, b"" if name.endswith("/") else b"x")])
                self.assert_clean_failure(data)

    def test_reject_reserved_devices_in_any_component(self):
        for device in ["CON", "PRN", "AUX", "NUL"] + [
                f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)]:
            for name in (device.lower(), f"d/{device.title()}.txt", device + "/"):
                with self.subTest(name=name):
                    self.assert_clean_failure(make_zip([(name, b"")]))

    def test_case_duplicates_and_prefix_collisions_in_both_orders(self):
        groups = [[("Readme", b"x"), ("README", b"y")],
                  [("a/", b""), ("A/", b"")], [("a", b"x"), ("A/", b"")],
                  [("a", b"x"), ("A/b", b"y")],
                  [("a/b/c", b"y"), ("A/B", b"x")],
                  [("same", b"x"), ("same", b"x")]]
        for entries in groups:
            for ordered in (entries, list(reversed(entries))):
                with self.subTest(entries=ordered):
                    self.assert_clean_failure(make_zip(ordered))

    def test_explicit_directory_can_follow_implicit_parent(self):
        self.write_zip([("a/b/file", b"x"), ("a/b/", b""), ("a/", b"")])
        self.assertEqual(extract_archive(self.archive, self.destination)["file_count"], 1)
        self.assertEqual((self.destination / "a/b/file").read_bytes(), b"x")

    def test_reject_unix_symlinks_and_special_files(self):
        for file_type in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFBLK, stat.S_IFCHR):
            info = zipfile.ZipInfo("special")
            info.create_system = 3
            info.external_attr = (file_type | 0o777) << 16
            with self.subTest(file_type=file_type):
                self.assert_clean_failure(make_zip([(info, b"target")]))

    def test_unix_type_and_directory_flag_consistency(self):
        invalid = [("file", stat.S_IFDIR << 16),
                   ("dir/", stat.S_IFREG << 16 | 0x10),
                   ("file", 0x10), ("dir/", 0o755 << 16),
                   ("file", stat.S_IFREG << 16 | 0x10)]
        for name, attributes in invalid:
            info = zipfile.ZipInfo(name)
            info.external_attr = attributes
            with self.subTest(name=name, attributes=attributes):
                self.assert_clean_failure(make_zip([(info, b"")]))
        directory = zipfile.ZipInfo("plain/")
        directory.external_attr = 0o755 << 16 | 0x10
        file = zipfile.ZipInfo("plain/file")
        file.external_attr = 0o644 << 16
        self.write_zip([(directory, b""), (file, b"x")])
        self.assertEqual(inspect_archive(self.archive)["file_count"], 1)

    def test_encryption_flags(self):
        for flags in (1, 0x40, 0x2000):
            with self.subTest(flags=flags):
                self.assert_clean_failure(raw_zip("file", b"x", 1, binascii.crc32(b"x"),
                                                  zipfile.ZIP_STORED, flags=flags))

    def test_entry_count_exact_boundary_and_overflow(self):
        self.write_zip([(f"file{n}", b"") for n in range(64)])
        self.assertEqual(inspect_archive(self.archive)["file_count"], 64)
        self.assert_clean_failure(make_zip([(f"dir{n}/", b"") for n in range(65)]))

    def test_file_and_total_size_boundaries(self):
        payload = random.Random(42).randbytes(512 * 1024)
        self.write_zip([(f"f{n}", payload) for n in range(4)])
        self.assertEqual(extract_archive(self.archive, self.destination)["total_uncompressed_bytes"],
                         2 * 1024 * 1024)
        # Use a different absent destination for rejection assertions.
        self.destination = self.root / "another destination"
        self.assert_clean_failure(make_zip([("oversized", payload + b"x")]))
        self.assert_clean_failure(make_zip([(f"f{n}", payload) for n in range(4)] + [("extra", b"x")]))

    def test_compression_ratio_exact_boundary_and_overflow(self):
        size = 100
        for _ in range(20):
            compressed = raw_deflate(b"A" * size)
            if size == 100 * len(compressed):
                break
            size = 100 * len(compressed)
        else:
            self.fail("could not construct an exact ratio boundary")
        payload = b"A" * size
        self.archive.write_bytes(raw_zip("file", compressed, size, binascii.crc32(payload)))
        self.assertEqual(inspect_archive(self.archive)["total_uncompressed_bytes"], size)
        payload += b"A"
        self.assert_clean_failure(raw_zip("file", raw_deflate(payload), len(payload),
                                          binascii.crc32(payload)))
        self.assert_clean_failure(raw_zip("file", b"", 1, 0))

    def test_metadata_rejected_before_decompression(self):
        self.write_zip([("first", b"safe"), ("../late", b"invalid")],
                       compression=zipfile.ZIP_DEFLATED)
        with mock.patch.object(core, "_read_member", side_effect=AssertionError("payload read")):
            with self.assertRaises(SafeZipError):
                extract_archive(self.archive, self.destination)
        self.assertFalse(list(self.root.glob(".safezip-*")))

    def test_size_and_ratio_metadata_rejected_before_decompression(self):
        cases = [raw_zip("huge", b"x", 512 * 1024 + 1, 0),
                 raw_zip("ratio", b"x", 101, 0),
                 raw_zip("zero", b"", 1, 0),
                 make_zip([(f"f{n}", b"x" * (512 * 1024)) for n in range(4)]
                          + [("extra", b"x")])]
        with mock.patch.object(core, "_read_member", side_effect=AssertionError("payload read")):
            for data in cases:
                self.assert_clean_failure(data)

    def test_data_descriptors_and_local_zip64_are_supported(self):
        class NonSeekable(io.BytesIO):
            def seek(self, *args):
                raise OSError("not seekable")

        for stream in (io.BytesIO(), NonSeekable()):
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                with archive.open("binary", "w", force_zip64=True) as sink:
                    sink.write(bytes(range(256)))
            self.archive.write_bytes(stream.getvalue())
            self.assertEqual(inspect_archive(self.archive)["total_uncompressed_bytes"], 256)

    def test_zip64_end_records_are_supported(self):
        data = make_zip([("file", b"x")])
        ordinary_end = struct.unpack("<4s4H2IH", data[-22:])
        index_size, index_offset = ordinary_end[5:7]
        record_offset = len(data) - 22
        record = struct.pack("<4sQ2H2I4Q", b"PK\x06\x06", 44, 45, 45,
                             0, 0, 1, 1, index_size, index_offset)
        locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, record_offset, 1)
        end = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 65535, 65535,
                          0xFFFFFFFF, 0xFFFFFFFF, 0)
        self.archive.write_bytes(data[:-22] + record + locator + end)
        self.assertEqual(inspect_archive(self.archive)["total_uncompressed_bytes"], 1)

    def test_archive_comment_and_prepended_stub_do_not_affect_manifest(self):
        data = make_zip([("file", b"x")])
        self.archive.write_bytes(data)
        expected = inspect_archive(self.archive)
        stream = io.BytesIO(data)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.comment = b"offline example"
        self.archive.write_bytes(b"harmless prepended bytes" + stream.getvalue())
        self.assertEqual(inspect_archive(self.archive), expected)

    def test_forged_small_size_cannot_hide_deflate_bomb(self):
        encoder = zlib.compressobj(wbits=-15)
        parts = [encoder.compress(b"A" * 65536) for _ in range(128)]
        compressed = b"".join(parts) + encoder.flush()  # 8 MiB output, a small on-disk fixture.
        data = raw_zip("bomb", compressed, 1, binascii.crc32(b"A"))
        decoder_factory = zlib.decompressobj
        output_limits = []

        class BoundedDecoder:
            def __init__(self, *args):
                self.decoder = decoder_factory(*args)

            def decompress(self, data, max_length=0):
                output_limits.append(max_length)
                if not 0 < max_length <= 2:
                    raise AssertionError("unbounded decompression")
                return self.decoder.decompress(data, max_length)

            def __getattr__(self, name):
                return getattr(self.decoder, name)

        with mock.patch.object(core.zlib, "decompressobj", BoundedDecoder):
            self.assert_clean_failure(data)
        self.assertEqual(output_limits, [2, 2])

    def test_crc_failure_after_earlier_member_cleans_staging(self):
        data = bytearray(make_zip([("a-good", b"good"), ("z-bad", b"bad payload")]))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("z-bad")
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        data[offset] ^= 1
        self.assert_clean_failure(bytes(data))
        result = self.cli("extract", self.archive, "--dest", self.destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_existing_files_and_directories_are_preserved(self):
        original = self.write_zip([("payload", b"new")])
        for kind in ("file", "directory", "empty directory"):
            with self.subTest(kind=kind):
                destination = self.root / kind
                if kind == "file":
                    destination.write_bytes(b"keep")
                else:
                    destination.mkdir()
                    if kind == "directory":
                        (destination / "keep").write_bytes(b"keep")
                before = set(self.root.iterdir())
                with self.assertRaises(SafeZipError):
                    extract_archive(self.archive, destination)
                self.assertEqual(set(self.root.iterdir()), before)
                if kind == "file":
                    self.assertEqual(destination.read_bytes(), b"keep")
                elif kind == "directory":
                    self.assertEqual((destination / "keep").read_bytes(), b"keep")
                else:
                    self.assertEqual(list(destination.iterdir()), [])
                self.assertEqual(self.archive.read_bytes(), original)

    def test_source_cannot_be_used_as_destination(self):
        original = self.write_zip([("a", b"x")])
        with self.assertRaises(SafeZipError):
            extract_archive(self.archive, self.archive)
        self.assertEqual(self.archive.read_bytes(), original)

    def test_existing_dangling_destination_symlink_is_preserved(self):
        self.write_zip([("a", b"x")])
        target = self.root / "does not exist"
        try:
            self.destination.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this host does not permit creating symlinks")
        with self.assertRaises(SafeZipError):
            extract_archive(self.archive, self.destination)
        self.assertTrue(self.destination.is_symlink())
        self.assertFalse(target.exists())

    def test_racing_destination_is_never_replaced(self):
        self.write_zip([("a", b"x")])
        original_commit = core._commit_directory

        def racing_commit(staging, destination):
            destination.mkdir()
            (destination / "keep").write_bytes(b"keep")
            original_commit(staging, destination)

        with mock.patch.object(core, "_commit_directory", racing_commit):
            with self.assertRaises(SafeZipError):
                extract_archive(self.archive, self.destination)
        self.assertEqual((self.destination / "keep").read_bytes(), b"keep")
        self.assertFalse(list(self.root.glob(".safezip-*")))

    def test_atomic_rename_primitive_cannot_replace_empty_directory(self):
        staging = self.root / "staging"
        staging.mkdir()
        (staging / "new").write_bytes(b"new")
        self.destination.mkdir()
        # Model an arrival after the user-space existence check.
        with mock.patch.object(core.os.path, "lexists", return_value=False):
            with self.assertRaises(OSError):
                core._commit_directory(staging, self.destination)
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual((staging / "new").read_bytes(), b"new")

    def test_staging_write_failure_leaves_no_destination(self):
        self.write_zip([("a", b"x"), ("b", b"y")])
        with mock.patch.object(core, "_read_member", side_effect=OSError("simulated write failure")):
            with self.assertRaises(SafeZipError):
                extract_archive(self.archive, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".safezip-*")))

    def test_missing_parent_does_not_create_directories(self):
        self.write_zip([("a", b"x")])
        missing_parent = self.root / "missing"
        with self.assertRaises(SafeZipError):
            extract_archive(self.archive, missing_parent / "destination")
        self.assertFalse(missing_parent.exists())

    def test_truncated_and_non_zip_data_controlled(self):
        valid = make_zip([("file", b"bytes")], compression=zipfile.ZIP_DEFLATED)
        for data in (b"", b"not a zip", valid[:-1], valid[:25], valid + b"trailing"):
            with self.subTest(length=len(data)):
                self.assert_clean_failure(data)

    def test_bad_deflate_directory_payload_and_unsupported_compression(self):
        self.assert_clean_failure(raw_zip("bad", b"not deflate", 3, 0))
        self.assert_clean_failure(raw_zip("truncated", raw_deflate(b"ok")[:-1], 2,
                                          binascii.crc32(b"ok")))
        self.assert_clean_failure(raw_zip("extra", raw_deflate(b"ok") + b"x", 2,
                                          binascii.crc32(b"ok")))
        self.assert_clean_failure(raw_zip("dir/", raw_deflate(b"hidden"), 0, 0,
                                          attr=(stat.S_IFDIR | 0o755) << 16 | 0x10))
        self.assert_clean_failure(raw_zip("bzip", b"data", 4, 0, method=zipfile.ZIP_BZIP2))

    def test_local_header_mismatch_and_encryption(self):
        original = make_zip([("file", b"bytes")])
        for offset, value in ((6, 1), (8, 8), (30, ord("X"))):
            data = bytearray(original)
            data[offset] = value
            with self.subTest(offset=offset):
                self.assert_clean_failure(bytes(data))

    def test_unsupported_zip_version_is_a_controlled_failure(self):
        data = bytearray(make_zip([("file", b"bytes")]))
        central_offset = data.index(b"PK\x01\x02")
        data[central_offset + 6] = 255
        self.assert_clean_failure(bytes(data))
        result = self.cli("inspect", self.archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertNotIn(b"Traceback", result.stderr)

    def test_nested_crc_failure_removes_the_complete_staging_tree(self):
        data = bytearray(make_zip([("a/deep/tree/file", b"ok"),
                                   ("a/other/empty/", b""), ("z/last", b"bad")]))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("z/last")
        data[info.header_offset + 30 + len(info.filename)] ^= 1
        self.assert_clean_failure(bytes(data))

    def test_help_usage_missing_archive_and_invalid_destination_have_no_traceback(self):
        for arguments in (("--help",), ("inspect", "--help"), ("extract", "--help")):
            result = self.cli(*arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"usage:", result.stdout)
        for arguments in ((), ("unknown",), ("inspect", self.root / "missing.zip"),
                          ("extract", "missing.zip")):
            result = self.cli(*arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
            self.assertNotIn(b"Traceback", result.stderr)

    def test_readme_smoke_commands_run_with_included_archive(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        self.assertIn("python -m safezip --help", readme)
        commands = re.findall(r"^python -m safezip (?:inspect|extract) .+$", readme, re.MULTILINE)
        self.assertEqual(len(commands), 2)
        outputs = []
        for command in commands:
            arguments = shlex.split(command)[3:]
            self.assertTrue((ROOT / arguments[1]).is_file())
            if arguments[0] == "extract":
                self.assertEqual(arguments[2], "--dest")
                arguments[3] = str(self.destination)
            result = self.cli(*arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual((self.destination / "hello.txt").read_bytes(), b"Hello from SafeZip!\n")


if __name__ == "__main__":
    unittest.main()
