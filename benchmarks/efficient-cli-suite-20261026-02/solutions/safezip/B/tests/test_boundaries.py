"""Adversarial byte-level fixtures and real filesystem transaction boundaries."""

import binascii
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

from safezip import cli


ROOT = Path(__file__).resolve().parents[1]


def raw_zip(payload, *, compressed=None, declared=None, crc=None, method=8):
    """One file with independently chosen actual bytes and metadata."""
    if compressed is None:
        compressor = zlib.compressobj(wbits=-15)
        compressed = compressor.compress(payload) + compressor.flush()
    size = len(payload) if declared is None else declared
    checksum = binascii.crc32(payload) if crc is None else crc
    name = b"payload"
    local = struct.pack("<4s5H3L2H", b"PK\x03\x04", 20, 0, method, 0, 0,
                        checksum, len(compressed), size, len(name), 0) + name + compressed
    central = struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 20, 20, 0, method, 0, 0,
                          checksum, len(compressed), size, len(name), 0, 0, 0, 0, 0, 0) + name
    end = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, len(central), len(local), 0)
    return local + central + end


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="boundary ", dir=ROOT / ".tmp")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.archive = self.work / "input with spaces.zip"

    def command(self, *args):
        return subprocess.run([sys.executable, "-m", "safezip", *map(str, args)],
                              cwd=ROOT, capture_output=True, timeout=15)

    def reject(self, data):
        self.archive.write_bytes(data)
        before = set(self.work.iterdir())
        target = self.work / "absent"
        for args in [("inspect", self.archive),
                     ("extract", self.archive, "--dest", target)]:
            result = self.command(*args)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout, b"")
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertEqual(set(self.work.iterdir()), before)
            self.assertFalse(os.path.lexists(target))
            self.assertEqual(self.archive.read_bytes(), data)
        return result

    def write(self, members, compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(self.archive, "w", compression=compression) as archive:
            for name, payload in members:
                archive.writestr(name, payload)
        return self.archive.read_bytes()

    def test_forged_small_metadata_cannot_hide_a_bomb(self):
        compressor = zlib.compressobj(wbits=-15)
        parts = [compressor.compress(b"X" * 65536) for _ in range(256)]
        compressed = b"".join(parts) + compressor.flush()
        # Only a small compressed fixture is ever resident. Metadata claims
        # one byte, while the raw stream expands to 16 MiB.
        result = self.reject(raw_zip(b"X", compressed=compressed, declared=1))
        self.assertIn(b"actual decompressed bytes exceed quota", result.stderr)

    def test_metadata_rejected_before_invalid_deflate(self):
        result = self.reject(raw_zip(b"", compressed=b"!", declared=512 * 1024 + 1))
        self.assertIn(b"file exceeds 512 KiB", result.stderr)
        result = self.reject(raw_zip(b"x", compressed=b"", declared=1))
        self.assertIn(b"zero compressed size", result.stderr)
        self.reject(raw_zip(b"x", compressed=b"!", declared=1000))

    def test_ratio_exactly_100_and_just_above(self):
        for size in range(100, 20001, 100):
            payload = b"x" * size
            compressor = zlib.compressobj(wbits=-15)
            compressed = compressor.compress(payload) + compressor.flush()
            if size == 100 * len(compressed):
                break
        else:
            self.fail("no exact-ratio fixture")
        self.archive.write_bytes(raw_zip(payload, compressed=compressed))
        accepted = self.command("inspect", self.archive)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.reject(raw_zip(payload + b"x"))

    def test_unspecified_type_and_directory_flag_agreement(self):
        for name, mode, dos, accepted in [
            ("ordinary", 0, 0, True), ("directory/", 0, 16, True),
            ("directory/", 0, 0, False), ("ordinary", 0, 16, False),
            ("block", stat.S_IFBLK, 0, False),
        ]:
            with self.subTest(name=name, mode=mode, dos=dos):
                info = zipfile.ZipInfo(name)
                info.external_attr = ((mode | 0o600) << 16) | dos
                data = self.write([(info, b"")])
                if accepted:
                    result = self.command("inspect", self.archive)
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.reject(data)

    def test_local_headers_and_malformed_archives(self):
        original = raw_zip(b"data")
        for offset, value in [(6, 1), (8, 99), (30, ord("Q"))]:
            damaged = bytearray(original)
            damaged[offset] = value
            self.reject(bytes(damaged))
        for data in [b"", b"not a ZIP", original[:-1], original + b"extra"]:
            self.reject(data)
        damaged = bytearray(original)
        struct.pack_into("<H", damaged, len(damaged) - 12, 65)
        struct.pack_into("<H", damaged, len(damaged) - 14, 65)
        self.reject(bytes(damaged))
        self.reject(raw_zip(b"", crc=1, method=0, compressed=b""))

    def test_streaming_descriptors_and_small_zip64(self):
        class Unseekable(io.BytesIO):
            def seek(self, *args):
                raise OSError("streaming sink")
        buffer = Unseekable()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("directory/", b"")
            archive.writestr("directory/file", bytes(range(256)) * 100)
        self.archive.write_bytes(buffer.getvalue())
        result = self.command("extract", self.archive, "--dest", self.work / "streamed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.work / "streamed/directory/file").read_bytes(),
                         bytes(range(256)) * 100)
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            with archive.open("zip64", "w", force_zip64=True) as output:
                output.write(b"small ZIP64 payload")
        result = self.command("inspect", self.archive)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_no_replace_rename_and_failed_commit_cleanup(self):
        for directory in (False, True):
            source = self.work / ("source-dir" if directory else "source-file")
            source.mkdir()
            (source / "new").write_bytes(b"new")
            target = self.work / ("existing-dir" if directory else "existing-file")
            if directory:
                target.mkdir()
            else:
                target.write_bytes(b"existing")
            with self.assertRaises(OSError):
                cli._rename_absent(source, target)
            self.assertTrue(source.is_dir())
            self.assertEqual(list(target.iterdir()), []) if directory else self.assertEqual(
                target.read_bytes(), b"existing")
        self.write([("valid", b"verified")])
        before = set(self.work.iterdir())
        with mock.patch.object(cli, "_rename_absent", side_effect=OSError("commit failed")):
            with self.assertRaises(OSError):
                cli.extract(self.archive, self.work / "never published")
        self.assertEqual(set(self.work.iterdir()), before)

    def test_legal_names_reverse_parent_conflict_and_missing_parent(self):
        names = ["a" * 80, " space allowed", ".hidden", "a-b_c.9", "COM0", "LPT10.txt"]
        self.write([(name, b"binary\x00\xff") for name in names])
        result = self.command("extract", self.archive, "--dest", self.work / "legal")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in names:
            self.assertEqual((self.work / "legal" / name).read_bytes(), b"binary\x00\xff")
        for name in ["CON .txt", "LPT1 .log"]:
            self.reject(self.write([(name, b"device alias")]))
        self.reject(self.write([("P/child", b"x"), ("p", b"file")]))
        self.write([("valid", b"x")])
        before = set(self.work.iterdir())
        result = self.command("extract", self.archive, "--dest", self.work / "missing/dest")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(set(self.work.iterdir()), before)

    def test_help_usage_and_missing_archive(self):
        for args in [("--help",), ("inspect", "--help"), ("extract", "--help")]:
            result = self.command(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"usage:", result.stdout)
        for args in [(), ("extract", self.archive), ("inspect", self.archive)]:
            result = self.command(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
            self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
