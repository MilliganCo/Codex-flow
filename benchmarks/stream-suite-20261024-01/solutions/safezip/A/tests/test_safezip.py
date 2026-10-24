"""Offline acceptance/regression tests; every temporary path is inside the repo."""

import binascii
import hashlib
import io
import json
import os
from pathlib import Path
import random
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

from safezip import core


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".tmp"


def canonical(manifest):
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def member(name, payload=b"", *, mode=None, dos_directory=None, compression=zipfile.ZIP_STORED):
    info = zipfile.ZipInfo(name, (2024, 1, 2, 3, 4, 6))
    info.create_system = 3
    directory = name.endswith("/")
    if mode is None:
        mode = (stat.S_IFDIR | 0o755) if directory else (stat.S_IFREG | 0o644)
    if dos_directory is None:
        dos_directory = directory
    info.external_attr = (mode << 16) | (0x10 if dos_directory else 0)
    info.compress_type = compression
    return info, payload


def raw_zip(name=b"file.bin", data=b"abc", *, compressed=None, declared_size=None,
            method=zipfile.ZIP_STORED, flags=0, crc=None, external_attr=None):
    """Construct adversarial ZIPs without ZipFile repairing the chosen metadata."""
    if compressed is None:
        if method == zipfile.ZIP_DEFLATED:
            compressor = zlib.compressobj(wbits=-15)
            compressed = compressor.compress(data) + compressor.flush()
        else:
            compressed = data
    if declared_size is None:
        declared_size = len(data)
    if crc is None:
        crc = binascii.crc32(data)
    if external_attr is None:
        external_attr = (stat.S_IFREG | 0o644) << 16
    local = struct.pack("<4s5H3I2H", b"PK\x03\x04", 20, flags, method, 0, 0,
                        crc, len(compressed), declared_size, len(name), 0)
    central = struct.pack("<4s6H3I5H2I", b"PK\x01\x02", (3 << 8) | 20, 20,
                          flags, method, 0, 0, crc, len(compressed), declared_size,
                          len(name), 0, 0, 0, 0, external_attr, 0) + name
    body = local + name + compressed
    end = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 1, 1, len(central), len(body), 0)
    return body + central + end


class SafeZipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(exist_ok=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="safezip-tests-", dir=SCRATCH)
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.archive = self.work / "archive with spaces.zip"
        self.destination = self.work / "new directory"

    def write_archive(self, members):
        with zipfile.ZipFile(self.archive, "w") as zipped:
            for info, payload in members:
                zipped.writestr(info, payload)

    def command(self, *args):
        return subprocess.run([sys.executable, "-m", "safezip", *map(str, args)],
                              cwd=ROOT, capture_output=True, timeout=15)

    def assert_rejected(self):
        before = self.archive.read_bytes()
        contents = set(self.work.iterdir())
        for arguments in (("inspect", self.archive),
                          ("extract", self.archive, "--dest", self.destination)):
            result = self.command(*arguments)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"safezip:", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertFalse(self.destination.exists())
            self.assertEqual(self.archive.read_bytes(), before)
            self.assertEqual(set(self.work.iterdir()), contents)

    def test_valid_manifest_exact_output_and_byte_exact_extraction(self):
        binary = bytes(range(256)) * 7 + b"\x00\xff\r\n"
        text = b"Hello, SafeZip!\n"
        self.write_archive([
            member("Folder/binary.bin", binary, compression=zipfile.ZIP_DEFLATED),
            member("empty.bin"), member("Folder/"), member("Folder/read me.txt", text),
        ])
        before = self.archive.read_bytes()
        before_directory = set(self.work.iterdir())
        inspected = self.command("inspect", self.archive)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(set(self.work.iterdir()), before_directory)
        expected = {
            "schema": 1,
            "entries": [
                {"path": "Folder", "kind": "dir", "size": 0, "sha256": None},
                {"path": "Folder/binary.bin", "kind": "file", "size": len(binary), "sha256": hashlib.sha256(binary).hexdigest()},
                {"path": "Folder/read me.txt", "kind": "file", "size": len(text), "sha256": hashlib.sha256(text).hexdigest()},
                {"path": "empty.bin", "kind": "file", "size": 0, "sha256": hashlib.sha256(b"").hexdigest()},
            ],
            "file_count": 3,
            "total_uncompressed_bytes": len(binary) + len(text),
        }
        self.assertEqual(inspected.stdout, canonical(expected))
        extracted = self.command("extract", self.archive, "--dest", self.destination)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        self.assertEqual(extracted.stdout, inspected.stdout)
        self.assertEqual(inspected.stderr + extracted.stderr, b"")
        self.assertEqual((self.destination / "Folder/binary.bin").read_bytes(), binary)
        self.assertEqual((self.destination / "Folder/read me.txt").read_bytes(), text)
        self.assertEqual((self.destination / "empty.bin").read_bytes(), b"")
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertEqual(list(self.work.glob(".safezip-*")), [])

    def test_empty_archive(self):
        self.write_archive([])
        expected = canonical({"schema": 1, "entries": [], "file_count": 0, "total_uncompressed_bytes": 0})
        for result in (self.command("inspect", self.archive),
                       self.command("extract", self.archive, "--dest", self.destination)):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_order_and_timestamp_determinism(self):
        items = [member("z.txt", b"z"), member("sub/"), member("sub/a.txt", b"a")]
        self.write_archive(items)
        first = self.command("inspect", self.archive)
        for info, _ in items:
            info.date_time = (2030, 6, 7, 8, 9, 10)
        self.write_archive(reversed(items))
        second = self.command("inspect", self.archive)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_portable_names_and_component_boundaries(self):
        paths = ["a" * 80, "A_z. -09", ".hidden", " leading", "COM0.txt", "LPT10", "conifer"]
        self.write_archive([member(name, b"x") for name in paths])
        result = self.command("extract", self.archive, "--dest", self.destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in paths:
            self.assertEqual((self.destination / name).read_bytes(), b"x")

    def test_reject_absolute_drive_unc_backslash_names(self):
        for name in ["/escape", "C:/escape", "C:escape", "//server/share", "\\\\server\\share", "dir\\file", "dir/x:y"]:
            with self.subTest(name=name):
                # ZipInfo normalizes backslashes on Windows; encode raw headers.
                self.archive.write_bytes(raw_zip(name.encode("ascii")))
                self.assert_rejected()

    def test_reject_dot_empty_and_nonportable_components(self):
        for name in ["", ".", "..", "a/../b", "./file", "a/./b", "a//b", "a//", "a///",
                     "x.", "x ", "a/ /b", "a" * 81, "caf\u00e9", "tab\tname", "star*", "question?", "nul\x00tail"]:
            with self.subTest(name=name):
                if "\x00" in name:
                    self.archive.write_bytes(raw_zip(name.encode("ascii")))
                else:
                    self.write_archive([member(name, b"x")])
                self.assert_rejected()

    def test_reject_reserved_device_names_and_extensions(self):
        names = ["CON", "prn.txt", "Aux.a.b", "nUl", "COM1", "com9.log", "LPT1.txt", "lpt9", "a/CoN.txt"]
        for name in names:
            with self.subTest(name=name):
                self.write_archive([member(name)])
                self.assert_rejected()

    def test_reject_casefold_duplicates_collisions_and_file_parents(self):
        cases = [
            [member("A"), member("a")],
            [member("Dir/"), member("dir")],
            [member("file"), member("FILE/child")],
            [member("FILE/child"), member("file")],
            [member("a/b"), member("A/B/")],
        ]
        for items in cases:
            with self.subTest(names=[i.filename for i, _ in items]):
                self.write_archive(items)
                self.assert_rejected()

    def test_implicit_parent_and_explicit_directory_share_a_tree(self):
        self.write_archive([member("a/b/file", b"abc"), member("a/"), member("a/b/")])
        manifest = core.extract_archive(self.archive, self.destination)
        self.assertEqual((self.destination / "a/b/file").read_bytes(), b"abc")
        self.assertEqual(len(manifest["entries"]), 3)

    def test_reject_unix_special_types(self):
        for mode in [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK]:
            with self.subTest(mode=mode):
                self.write_archive([member("special", b"target", mode=mode | 0o777)])
                self.assert_rejected()

    def test_type_zero_and_directory_flag_agreement(self):
        self.write_archive([member("folder/", mode=0o755), member("folder/plain", b"x", mode=0o600)])
        self.assertEqual(self.command("inspect", self.archive).returncode, 0)
        for item in [member("folder/", mode=0, dos_directory=False),
                     member("plain", mode=0, dos_directory=True),
                     member("folder/", mode=stat.S_IFREG | 0o644),
                     member("plain", mode=stat.S_IFDIR | 0o755)]:
            with self.subTest(name=item[0].filename, attr=item[0].external_attr):
                self.write_archive([item])
                self.assert_rejected()

    def test_reject_encryption_flags(self):
        for flag in [1, 0x40, 0x2000]:
            with self.subTest(flag=flag):
                self.archive.write_bytes(raw_zip(flags=flag))
                self.assert_rejected()

    def test_entry_limit_includes_directories(self):
        self.write_archive([member(f"d{index}/") for index in range(64)])
        self.assertEqual(self.command("inspect", self.archive).returncode, 0)
        self.write_archive([member(f"d{index}/") for index in range(65)])
        self.assert_rejected()

    def test_file_and_total_size_boundaries(self):
        # Stored payloads avoid the independent compression-ratio limit.
        payload = bytes(range(256)) * (core.MAX_FILE_BYTES // 256)
        self.write_archive([member(f"file{index}", payload) for index in range(4)])
        manifest, _ = core.validate_archive(self.archive)
        self.assertEqual(manifest["total_uncompressed_bytes"], core.MAX_TOTAL_BYTES)
        boundary_destination = self.work / "boundary"
        core.extract_archive(self.archive, boundary_destination)
        for index in range(4):
            self.assertEqual((boundary_destination / f"file{index}").read_bytes(), payload)
        self.write_archive([member("huge", payload + b"x")])
        self.assert_rejected()
        self.write_archive([member(f"file{index}", payload) for index in range(4)] + [member("extra", b"x")])
        self.assert_rejected()

    def test_compression_ratio_boundary_and_empty_ratio(self):
        for size, compressed_size, valid in [(100, 1, True), (101, 1, False), (1, 0, False), (0, 0, True)]:
            with self.subTest(size=size, compressed_size=compressed_size):
                info, _ = member("x")
                info.file_size = size
                info.compress_size = compressed_size
                if valid:
                    core._metadata([info])
                else:
                    with self.assertRaises(core.SafeZipError):
                        core._metadata([info])
        self.write_archive([member("compressed", b"x" * 20000, compression=zipfile.ZIP_DEFLATED)])
        self.assert_rejected()
        self.write_archive([member("empty", compression=zipfile.ZIP_DEFLATED)])
        self.assertEqual(self.command("inspect", self.archive).returncode, 0)

    def test_metadata_rejection_happens_before_decompression(self):
        self.archive.write_bytes(raw_zip(declared_size=core.MAX_FILE_BYTES + 1, method=8))
        with mock.patch.object(core.zlib, "decompressobj", side_effect=AssertionError("must not decompress")):
            with self.assertRaises(core.SafeZipError):
                core.validate_archive(self.archive)

    def test_actual_decompression_is_bounded_when_metadata_lies(self):
        compressor = zlib.compressobj(wbits=-15)
        parts = [compressor.compress(b"x" * 65536) for _ in range(64)]
        compressed = b"".join(parts) + compressor.flush()
        self.archive.write_bytes(raw_zip(data=b"x", compressed=compressed, declared_size=1, method=8))
        decompressor = zlib.decompressobj
        calls = []

        class TrackingDecoder:
            def __init__(self, *args):
                self.inner = decompressor(*args)

            def decompress(self, chunk, limit):
                calls.append(limit)
                return self.inner.decompress(chunk, limit)

            def __getattr__(self, name):
                return getattr(self.inner, name)

        with mock.patch.object(core.zlib, "decompressobj", TrackingDecoder):
            with self.assertRaises(core.SafeZipError):
                core.validate_archive(self.archive)
        self.assertEqual(calls, [2])
        self.assert_rejected()

    def test_reject_damaged_crc_for_stored_and_deflated(self):
        for method in [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED]:
            with self.subTest(method=method):
                self.archive.write_bytes(raw_zip(data=b"content", method=method, crc=1))
                self.assert_rejected()

    def test_reject_truncated_and_invalid_deflate_streams(self):
        for compressed in [b"", b"bad stream", b"\x03", b"\x03\x00garbage"]:
            with self.subTest(compressed=compressed):
                self.archive.write_bytes(raw_zip(data=b"", method=8, compressed=compressed))
                self.assert_rejected()

    def test_late_invalid_member_and_late_crc_failure_are_atomic(self):
        self.write_archive([member("good", b"keep"), member("../escape", b"bad")])
        self.assert_rejected()
        self.write_archive([member("good", b"keep"), member("late", b"damage")])
        encoded = bytearray(self.archive.read_bytes())
        with zipfile.ZipFile(self.archive) as zipped:
            late = zipped.getinfo("late")
            offset = late.header_offset + 30 + len(late.filename)
        encoded[offset] ^= 1
        self.archive.write_bytes(encoded)
        self.assert_rejected()
        self.assertFalse((self.work.parent / "escape").exists())

    def test_existing_destination_file_and_directory_are_preserved(self):
        self.write_archive([member("good", b"data")])
        before = self.archive.read_bytes()
        self.destination.write_bytes(b"existing file")
        result = self.command("extract", self.archive, "--dest", self.destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.destination.read_bytes(), b"existing file")
        self.destination.unlink()
        self.destination.mkdir()
        marker = self.destination / "marker"
        marker.write_bytes(b"existing directory")
        result = self.command("extract", self.archive, "--dest", self.destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_bytes(), b"existing directory")
        self.assertEqual(list(self.destination.iterdir()), [marker])
        self.assertEqual(self.archive.read_bytes(), before)

    def test_dangling_destination_symlink_is_preserved(self):
        self.write_archive([])
        try:
            self.destination.symlink_to(self.work / "missing", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable to this account")
        result = self.command("extract", self.archive, "--dest", self.destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.destination.is_symlink())
        self.assertFalse((self.work / "missing").exists())

    def test_write_failure_removes_staging_and_preserves_other_files(self):
        self.write_archive([member("a", b"first"), member("b", b"second")])
        sentinel = self.work / "sentinel"
        sentinel.write_bytes(b"untouched")
        before = self.archive.read_bytes()
        real_open = Path.open

        def fail_second(path, *args, **kwargs):
            if path.name == "b" and args and args[0] == "xb":
                raise OSError("injected disk write failure")
            return real_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", fail_second):
            with self.assertRaises(OSError):
                core.extract_archive(self.archive, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.work.glob(".safezip-*")), [])
        self.assertEqual(sentinel.read_bytes(), b"untouched")
        self.assertEqual(self.archive.read_bytes(), before)

    def test_racing_destination_is_not_replaced_and_staging_is_removed(self):
        self.write_archive([member("a", b"data")])
        actual_rename = core._rename_absent

        def race(source, destination):
            destination.mkdir()  # Even an empty directory must never be replaced.
            actual_rename(source, destination)

        with mock.patch.object(core, "_rename_absent", race):
            with self.assertRaises(OSError):
                core.extract_archive(self.archive, self.destination)
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual(list(self.work.glob(".safezip-*")), [])

    def test_help_space_paths_and_controlled_errors(self):
        for arguments in [("--help",), ("inspect", "--help"), ("extract", "--help")]:
            result = self.command(*arguments)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"usage:", result.stdout)
        for arguments in [(), ("unknown",), ("inspect", self.work / "missing.zip"),
                          ("extract", self.archive)]:
            result = self.command(*arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
            self.assertNotIn(b"Traceback", result.stderr)
        self.archive.write_bytes(b"not a zip")
        self.assert_rejected()

    def test_zip64_local_header_and_data_descriptor(self):
        with zipfile.ZipFile(self.archive, "w", compression=8) as zipped:
            with zipped.open("small", "w", force_zip64=True) as stream:
                stream.write(b"small payload")
        self.assertEqual(self.command("inspect", self.archive).returncode, 0)

        class Unseekable(io.BytesIO):
            def seek(self, *args):
                raise io.UnsupportedOperation("not seekable")

        buffer = Unseekable()
        with zipfile.ZipFile(buffer, "w", compression=8) as zipped:
            zipped.writestr("descriptor", b"streamed payload")
        self.archive.write_bytes(buffer.getvalue())
        self.assertEqual(self.command("inspect", self.archive).returncode, 0)
        damaged = bytearray(buffer.getvalue())
        descriptor = damaged.index(b"PK\x07\x08")
        damaged[descriptor + 4] ^= 1
        self.archive.write_bytes(damaged)
        self.assert_rejected()

    def test_reject_unsupported_compression_and_directory_payloads(self):
        for method in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            with self.subTest(method=method):
                self.archive.write_bytes(raw_zip(method=method))
                self.assert_rejected()
        self.write_archive([member("directory/", b"unexpected")])
        self.assert_rejected()

    def test_small_malformed_inputs_have_controlled_exits(self):
        generator = random.Random(90210)
        for length in [0, 1, 4, 22, 128, 1024]:
            with self.subTest(length=length):
                self.archive.write_bytes(generator.randbytes(length))
                self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
