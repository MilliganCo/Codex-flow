"""Finite offline acceptance checks; all temporary files stay in this workspace."""

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

from safezip import SafeZipError, extract_archive, inspect_archive, manifest_json
from safezip import core

ROOT = Path(__file__).absolute().parents[1]


class SafeZipTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="safezip tests ", dir=ROOT / ".tmp")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.serial = 0

    def make_zip(self, entries, compression=zipfile.ZIP_STORED, timestamp=(2020, 1, 1, 0, 0, 0)):
        self.serial += 1
        path = self.base / f"archive {self.serial}.zip"
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for entry in entries:
                name, payload = entry[:2]
                info = zipfile.ZipInfo(name, date_time=timestamp)
                # Windows ZipInfo normalizes backslashes when constructed; fixtures
                # must retain the exact hostile name on disk to test rejection.
                info.filename = name
                info.create_system = 3
                directory = name.endswith("/")
                mode = (stat.S_IFDIR | 0o755) if directory else (stat.S_IFREG | 0o644)
                info.external_attr = (mode << 16) | (0x10 if directory else 0)
                if len(entry) >= 3:
                    info.external_attr = entry[2]
                archive.writestr(info, payload, compress_type=compression)
        return path

    def cli(self, *args, cwd=ROOT):
        return subprocess.run(
            [sys.executable, "-m", "safezip", *map(os.fspath, args)],
            cwd=cwd, capture_output=True, timeout=15,
        )

    def rejected(self, archive):
        original = archive.read_bytes()
        before = set(self.base.iterdir())
        destination = self.base / "fresh destination"
        with self.assertRaises((SafeZipError, zipfile.BadZipFile, zlib.error, OSError)):
            inspect_archive(archive)
        with self.assertRaises((SafeZipError, zipfile.BadZipFile, zlib.error, OSError)):
            extract_archive(archive, destination)
        self.assertFalse(os.path.lexists(destination))
        self.assertEqual(before, set(self.base.iterdir()), "staging or outside output leaked")
        self.assertEqual(original, archive.read_bytes())

    def patch_fields(self, archive, *, index=0, central=(), local=()):
        with zipfile.ZipFile(archive) as reader:
            local_offset = reader.infolist()[index].header_offset
            central_offset = reader.start_dir
        data = bytearray(archive.read_bytes())
        for _ in range(index):
            lengths = struct.unpack_from("<3H", data, central_offset + 28)
            central_offset += 46 + sum(lengths)
        for offset, code, value in central:
            struct.pack_into(code, data, central_offset + offset, value)
        for offset, code, value in local:
            struct.pack_into(code, data, local_offset + offset, value)
        archive.write_bytes(data)

    def test_valid_stored_and_deflated_binary_bytes(self):
        payload = bytes(range(256)) * 3 + b"\x00\xff\r\n"
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                archive = self.make_zip([
                    ("docs/", b""), ("docs/hello.txt", b"hello\n"),
                    ("binary.dat", payload), ("empty.bin", b""),
                ], compression)
                before = archive.read_bytes()
                manifest = inspect_archive(archive)
                destination = self.base / f"output {compression}"
                self.assertEqual(manifest, extract_archive(archive, destination))
                self.assertEqual(payload, (destination / "binary.dat").read_bytes())
                self.assertEqual(b"hello\n", (destination / "docs/hello.txt").read_bytes())
                self.assertEqual(b"", (destination / "empty.bin").read_bytes())
                self.assertEqual(3, manifest["file_count"])
                self.assertEqual(len(payload) + 6, manifest["total_uncompressed_bytes"])
                binary = manifest["entries"][0]
                self.assertEqual(hashlib.sha256(payload).hexdigest(), binary["sha256"])
                self.assertEqual(before, archive.read_bytes())
                self.assertFalse(list(self.base.glob(".safezip-*")))

    def test_empty_archive(self):
        archive = self.make_zip([])
        expected = {"schema": 1, "entries": [], "file_count": 0, "total_uncompressed_bytes": 0}
        self.assertEqual(expected, inspect_archive(archive))
        destination = self.base / "empty output"
        self.assertEqual(expected, extract_archive(archive, destination))
        self.assertEqual([], list(destination.iterdir()))

    def test_exact_manifest_stdout_and_command_agreement(self):
        archive = self.make_zip([("z/", b""), ("a.bin", b"\x00\xff"), ("z/file", b"")])
        expected = {
            "schema": 1,
            "entries": [
                {"path": "a.bin", "kind": "file", "size": 2,
                 "sha256": hashlib.sha256(b"\x00\xff").hexdigest()},
                {"path": "z", "kind": "dir", "size": 0, "sha256": None},
                {"path": "z/file", "kind": "file", "size": 0,
                 "sha256": hashlib.sha256(b"").hexdigest()},
            ],
            "file_count": 2, "total_uncompressed_bytes": 2,
        }
        wire = (json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        inspected = self.cli("inspect", archive)
        extracted = self.cli("extract", archive, "--dest", self.base / "new output")
        for result in (inspected, extracted):
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(b"", result.stderr)
            self.assertEqual(wire, result.stdout)
        self.assertEqual(wire, manifest_json(expected).encode())

    def test_order_and_timestamp_determinism(self):
        entries = [("b.bin", b"second"), ("folder/", b""), ("folder/a.bin", b"first")]
        first = self.make_zip(entries)
        second = self.make_zip(list(reversed(entries)), timestamp=(2025, 12, 31, 23, 59, 58))
        self.assertEqual(manifest_json(inspect_archive(first)), manifest_json(inspect_archive(second)))

    def test_portable_names_and_80_character_boundary(self):
        names = ["a" * 80, "space name/file_1-2.txt", ".hidden", "COM0.txt", "LPT10.txt", "a..b"]
        archive = self.make_zip([(name, b"ok") for name in names])
        self.assertEqual(sorted(names), [entry["path"] for entry in inspect_archive(archive)["entries"]])
        destination = self.base / "portable output"
        extract_archive(archive, destination)
        for name in names:
            self.assertEqual(b"ok", destination.joinpath(*name.split("/")).read_bytes())

    def test_nonportable_names(self):
        bad_names = [
            "/absolute", "C:/drive", "C:relative", "//server/share", "\\\\server\\share",
            "a\\b", "a:b", ".", "..", "a/./b", "a/../b", "a//b", "a//", "/",
            "a.", "a ", "a" * 81, "non-ascii-é", "a\tb", "a?b", "a*b", "a|b",
            "CON", "con.txt", "pRn.log", "AUX", "NUL.data", "COM1", "com9.txt",
            "LPT1", "lpt9.bin", "parent/CON.txt/child", "CON .txt",
        ]
        for name in bad_names:
            with self.subTest(name=name):
                self.rejected(self.make_zip([(name, b"")]))

    def test_nul_in_original_name(self):
        archive = self.make_zip([("safeX.txt", b"payload")])
        archive.write_bytes(archive.read_bytes().replace(b"safeX.txt", b"safe\x00.txt"))
        self.rejected(archive)

    def test_duplicates_and_file_parent_conflicts_in_both_orders(self):
        pairs = [("A", "a"), ("a", "a/"), ("Dir/", "dir/"),
                 ("A", "a/child"), ("a/b", "A"), ("a/b", "A/B")]
        for pair in pairs:
            for names in (pair, tuple(reversed(pair))):
                with self.subTest(names=names):
                    self.rejected(self.make_zip([(name, b"") for name in names]))

    def test_special_file_types(self):
        for file_type in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK):
            with self.subTest(file_type=file_type):
                self.rejected(self.make_zip([("special", b"target", (file_type | 0o644) << 16)]))

    def test_type_bits_and_directory_flag_agreement(self):
        bad = [
            ("file", b"", 0x10), ("dir/", b"", 0o600 << 16),
            ("dir/", b"", ((stat.S_IFREG | 0o644) << 16) | 0x10),
            ("file", b"", (stat.S_IFDIR | 0o755) << 16),
            ("file", b"", ((stat.S_IFREG | 0o644) << 16) | 0x10),
            ("dir/", b"payload", ((stat.S_IFDIR | 0o755) << 16) | 0x10),
        ]
        for entry in bad:
            with self.subTest(entry=entry):
                self.rejected(self.make_zip([entry]))
        archive = self.make_zip([("file", b"ok", 0o600 << 16), ("dir/", b"", 0x10)])
        self.assertEqual(1, inspect_archive(archive)["file_count"])

    def test_encryption_flags_rejected_before_payload(self):
        for flag in (1, 0x40, 0x2000):
            archive = self.make_zip([("file", b"data")])
            self.patch_fields(archive, central=[(8, "<H", flag)], local=[(6, "<H", flag)])
            with mock.patch.object(core, "_stream", side_effect=AssertionError("decompressed encrypted entry")):
                self.rejected(archive)

    def test_unsupported_compression(self):
        archive = self.make_zip([("file", b"data")])
        self.patch_fields(archive, central=[(10, "<H", 12)], local=[(8, "<H", 12)])
        self.rejected(archive)

    def test_entry_count_inclusive_boundary(self):
        self.assertEqual(64, inspect_archive(self.make_zip([(f"f{i}", b"") for i in range(64)]))["file_count"])
        self.rejected(self.make_zip([(f"f{i}", b"") for i in range(65)]))
        self.rejected(self.make_zip([(f"d{i}/", b"") for i in range(65)]))

    def test_file_size_inclusive_boundary(self):
        payload = bytes(range(256)) * 2048
        archive = self.make_zip([("maximum", payload)])
        self.assertEqual(524288, inspect_archive(archive)["total_uncompressed_bytes"])
        self.rejected(self.make_zip([("too-large", payload + b"!")]))

    def test_total_size_inclusive_boundary(self):
        payload = bytes(range(256)) * 2048
        entries = [(f"f{i}", payload) for i in range(4)]
        self.assertEqual(2097152, inspect_archive(self.make_zip(entries))["total_uncompressed_bytes"])
        self.rejected(self.make_zip(entries + [("extra", b"!")]))

    def test_compression_ratio_and_zero_compressed_size(self):
        self.rejected(self.make_zip([("bomb", b"A" * 50000)], zipfile.ZIP_DEFLATED))
        archive = self.make_zip([("file", b"A")], zipfile.ZIP_DEFLATED)
        self.patch_fields(archive, central=[(20, "<L", 0)], local=[(18, "<L", 0)])
        self.rejected(archive)
        # Find an actual deflate stream on the inclusive ratio boundary.
        exact = None
        for size in range(100, 3001, 100):
            compressor = zlib.compressobj(wbits=-15)
            packed = compressor.compress(b"A" * size) + compressor.flush()
            if size == 100 * len(packed):
                exact = size
                break
        self.assertIsNotNone(exact, "fixture must exercise ratio exactly 100")
        self.assertEqual(exact, inspect_archive(self.make_zip([("exact", b"A" * exact)], 8))["total_uncompressed_bytes"])

    def test_metadata_limits_checked_before_decompression(self):
        archive = self.make_zip([("late", b"A" * 600000)], zipfile.ZIP_DEFLATED)
        with mock.patch.object(core.zlib, "decompressobj", side_effect=AssertionError("decoder created")):
            self.rejected(archive)

    def test_underreported_size_stops_decoder_with_bounded_output(self):
        archive = self.make_zip([("hidden-bomb", b"A" * (4 * 1024 * 1024))], 8)
        crc = zlib.crc32(b"A")
        self.patch_fields(archive, central=[(24, "<L", 1), (16, "<L", crc)],
                          local=[(22, "<L", 1), (14, "<L", crc)])
        real_factory = zlib.decompressobj
        decoders = []

        class BoundedDecoder:
            def __init__(self, *args):
                self.decoder = real_factory(*args)
                self.produced = 0
                decoders.append(self)

            def decompress(self, data, limit):
                if not 0 < limit <= core.CHUNK_BYTES:
                    raise AssertionError("unbounded decompression")
                result = self.decoder.decompress(data, limit)
                self.produced += len(result)
                return result

            def __getattr__(self, name):
                return getattr(self.decoder, name)

        with mock.patch.object(core.zlib, "decompressobj", BoundedDecoder):
            self.rejected(archive)
        self.assertEqual(2, len(decoders))
        self.assertTrue(all(decoder.produced <= 2 for decoder in decoders))

    def test_crc_corruption_and_late_failure_cleanup(self):
        archive = self.make_zip([("a-good", b"first"), ("z-bad", b"last payload")])
        with zipfile.ZipFile(archive) as reader:
            info = reader.infolist()[1]
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        data = bytearray(archive.read_bytes())
        data[offset] ^= 1
        archive.write_bytes(data)
        sentinel = self.base / "unrelated.txt"
        sentinel.write_bytes(b"untouched")
        self.rejected(archive)
        self.assertEqual(b"untouched", sentinel.read_bytes())
        result = self.cli("extract", archive, "--dest", self.base / "CLI fresh")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertFalse((self.base / "CLI fresh").exists())

    def test_late_invalid_member_does_not_write_anything(self):
        self.rejected(self.make_zip([("good", b"first"), ("../../outside", b"last")]))

    def test_existing_destinations_preserved(self):
        archive = self.make_zip([("file", b"new")])
        file = self.base / "existing file"
        file.write_bytes(b"old")
        empty = self.base / "empty directory"
        empty.mkdir()
        populated = self.base / "populated directory"
        populated.mkdir()
        (populated / "keep").write_bytes(b"keep")
        for destination in (file, empty, populated):
            with self.subTest(destination=destination):
                with self.assertRaises(SafeZipError):
                    extract_archive(archive, destination)
        self.assertEqual(b"old", file.read_bytes())
        self.assertEqual([], list(empty.iterdir()))
        self.assertEqual(b"keep", (populated / "keep").read_bytes())
        self.assertFalse(list(self.base.glob(".safezip-*")))

    def test_commit_rechecks_destination_and_cleans_staging(self):
        archive = self.make_zip([("file", b"new")])
        destination = self.base / "raced output"
        original_commit = core._commit

        def competing_commit(staging, final):
            final.mkdir()
            (final / "keep").write_bytes(b"competitor")
            original_commit(staging, final)

        with mock.patch.object(core, "_commit", competing_commit):
            with self.assertRaises(SafeZipError):
                extract_archive(archive, destination)
        self.assertEqual(b"competitor", (destination / "keep").read_bytes())
        self.assertFalse((destination / "file").exists())
        self.assertFalse(list(self.base.glob(".safezip-*")))

    def test_dangling_destination_rejected(self):
        archive = self.make_zip([("file", b"new")])
        destination = self.base / "dangling"
        try:
            destination.symlink_to(self.base / "does not exist", target_is_directory=True)
        except OSError:
            self.skipTest("platform does not grant symlink creation")
        with self.assertRaises(SafeZipError):
            extract_archive(archive, destination)
        self.assertTrue(destination.is_symlink())
        self.assertFalse(list(self.base.glob(".safezip-*")))

    def test_write_and_commit_failures_cleanup(self):
        archive = self.make_zip([("file", b"new")])
        destination = self.base / "fresh"
        with mock.patch.object(core, "_commit", side_effect=OSError("injected commit failure")):
            with self.assertRaises(OSError):
                extract_archive(archive, destination)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.base.glob(".safezip-*")))
        with mock.patch.object(core, "_stream", side_effect=OSError("injected write failure")):
            with self.assertRaises(OSError):
                extract_archive(archive, destination)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.base.glob(".safezip-*")))

    def test_malformed_and_truncated_archives_controlled(self):
        valid = self.make_zip([("file", b"data")])
        wire = valid.read_bytes()
        variants = [b"", b"not a zip", wire[:-1], wire[:30], wire[:-22]]
        for index, payload in enumerate(variants):
            with self.subTest(index=index):
                path = self.base / f"broken{index}.zip"
                path.write_bytes(payload)
                self.rejected(path)
                result = self.cli("inspect", path)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(b"", result.stdout)
                self.assertNotIn(b"Traceback", result.stderr)

    def test_local_central_disagreement(self):
        archive = self.make_zip([("file", b"data")])
        self.patch_fields(archive, local=[(22, "<L", 3)])
        self.rejected(archive)

    def test_small_zip64_local_header(self):
        path = self.base / "local zip64.zip"
        with zipfile.ZipFile(path, "w") as archive:
            with archive.open("file", "w", force_zip64=True) as sink:
                sink.write(b"small payload")
        self.assertEqual(13, inspect_archive(path)["total_uncompressed_bytes"])

    def test_zip64_central_directory_with_small_members(self):
        for entries in ([], [("file", b"small payload")]):
            archive = self.make_zip(entries)
            expected = inspect_archive(archive)
            wire = bytearray(archive.read_bytes())
            end_offset = len(wire) - 22
            end = struct.unpack_from("<4s4H2LH", wire, end_offset)
            record = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45,
                                 0, 0, end[4], end[4], end[5], end[6])
            locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, end_offset, 1)
            struct.pack_into("<HHLL", wire, end_offset + 8, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
            archive.write_bytes(wire[:end_offset] + record + locator + wire[end_offset:])
            self.assertEqual(expected, inspect_archive(archive))
            self.assertEqual(expected, extract_archive(archive, self.base / f"zip64 output {self.serial}"))

    def streaming_zip(self, force_zip64=False):
        class Unseekable(io.BytesIO):
            def seek(self, *args):
                raise io.UnsupportedOperation("stream")

        stream = Unseekable()
        payload = b"streamed payload\x00\xff" * 3
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            with archive.open("file", "w", force_zip64=force_zip64) as sink:
                sink.write(payload)
        self.serial += 1
        path = self.base / f"streaming{self.serial}.zip"
        path.write_bytes(stream.getvalue())
        return path, payload

    def test_streaming_data_descriptors_and_crc(self):
        for force_zip64 in (False, True):
            archive, payload = self.streaming_zip(force_zip64)
            expected = inspect_archive(archive)
            destination = self.base / f"stream output {force_zip64}"
            self.assertEqual(expected, extract_archive(archive, destination))
            self.assertEqual(payload, (destination / "file").read_bytes())
            wire = bytearray(archive.read_bytes())
            descriptor = wire.index(b"PK\x07\x08")
            wire[descriptor + 4] ^= 1
            archive.write_bytes(wire)
            self.rejected(archive)

    def test_unsigned_data_descriptor(self):
        archive, payload = self.streaming_zip()
        wire = bytearray(archive.read_bytes())
        descriptor = wire.index(b"PK\x07\x08")
        del wire[descriptor:descriptor + 4]
        end = len(wire) - 22
        central_offset = struct.unpack_from("<L", wire, end + 16)[0]
        struct.pack_into("<L", wire, end + 16, central_offset - 4)
        archive.write_bytes(wire)
        self.assertEqual(len(payload), inspect_archive(archive)["total_uncompressed_bytes"])

    def test_multichunk_deflate_stream(self):
        generator = random.Random(721)
        for payload in (generator.randbytes(524288), generator.randbytes(8192) * 64):
            archive = self.make_zip([("large.bin", payload)], 8)
            manifest = inspect_archive(archive)
            destination = self.base / f"multichunk {self.serial}"
            self.assertEqual(manifest, extract_archive(archive, destination))
            self.assertEqual(payload, (destination / "large.bin").read_bytes())
            self.assertEqual(hashlib.sha256(payload).hexdigest(), manifest["entries"][0]["sha256"])

    def test_native_commit_never_replaces_a_racing_empty_directory(self):
        archive = self.make_zip([("file", b"new")])
        destination = self.base / "racing empty directory"
        original_commit = core._commit

        def competing_commit(staging, final):
            final.mkdir()
            # Simulate the competitor arriving after the advisory existence check.
            # The real OS rename must still refuse replacement of this empty tree.
            with mock.patch.object(core.os.path, "lexists", return_value=False):
                original_commit(staging, final)

        with mock.patch.object(core, "_commit", competing_commit):
            with self.assertRaises(OSError):
                extract_archive(archive, destination)
        self.assertTrue(destination.is_dir())
        self.assertEqual([], list(destination.iterdir()))
        self.assertFalse(list(self.base.glob(".safezip-*")))

    def test_deflate_truncation_and_trailing_compressed_bytes(self):
        archive = self.make_zip([("file", b"valid compressed bytes")], 8)
        with zipfile.ZipFile(archive) as reader:
            compressed = reader.infolist()[0].compress_size
        self.patch_fields(archive, central=[(20, "<L", compressed - 1)], local=[(18, "<L", compressed - 1)])
        self.rejected(archive)
        archive = self.make_zip([("file", b"valid compressed bytes")], 8)
        wire = bytearray(archive.read_bytes())
        with zipfile.ZipFile(archive) as reader:
            central = reader.start_dir
            compressed = reader.infolist()[0].compress_size
        wire[central:central] = b"\x00"
        struct.pack_into("<L", wire, 18, compressed + 1)
        struct.pack_into("<L", wire, central + 1 + 20, compressed + 1)
        struct.pack_into("<L", wire, len(wire) - 22 + 16, central + 1)
        archive.write_bytes(wire)
        self.rejected(archive)

    def test_help_argument_errors_and_space_paths(self):
        for args in [("--help",), ("inspect", "--help"), ("extract", "--help")]:
            result = self.cli(*args)
            self.assertEqual(0, result.returncode)
            self.assertIn(b"usage:", result.stdout)
        for args in [(), ("unknown",), ("extract", "missing.zip"), ("inspect", "missing.zip")]:
            result = self.cli(*args)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"", result.stdout)
            self.assertNotIn(b"Traceback", result.stderr)
        archive = self.make_zip([("space dir/space file.bin", b"bytes")])
        destination = self.base / "output with spaces"
        result = self.cli("extract", archive, "--dest", destination)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"bytes", (destination / "space dir/space file.bin").read_bytes())

    def test_readme_commands_and_included_archive(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        self.assertIn("python -m safezip --help", readme)
        self.assertIn("python -m safezip inspect examples/sample.zip", readme)
        self.assertIn("python -m safezip extract examples/sample.zip --dest sample-output", readme)
        archive = ROOT / "examples/sample.zip"
        original = archive.read_bytes()
        inspect = self.cli("inspect", "examples/sample.zip")
        extract = self.cli("extract", "examples/sample.zip", "--dest", self.base / "README output")
        self.assertEqual(0, inspect.returncode, inspect.stderr)
        self.assertEqual(0, extract.returncode, extract.stderr)
        self.assertEqual(inspect.stdout, extract.stdout)
        self.assertEqual(original, archive.read_bytes())


if __name__ == "__main__":
    unittest.main()
