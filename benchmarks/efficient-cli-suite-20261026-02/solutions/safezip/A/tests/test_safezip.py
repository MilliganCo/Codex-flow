"""Offline regression tests. All temporary files stay inside this workspace."""

import binascii
import errno
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
from unittest.mock import patch
import warnings
import zipfile
import zlib

from safezip import SafeZipError, extract_archive, inspect_archive, manifest_bytes
from safezip import core


ROOT = Path(__file__).resolve().parents[1]


class SafeZipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".safezip-tests-", dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "archive with spaces.zip"
        self.destination = self.root / "new destination"

    def make_zip(self, entries, *, method=zipfile.ZIP_STORED, timestamp=(2024, 1, 1, 0, 0, 0)):
        """Entries are (name, bytes) or (ZipInfo, bytes)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)  # Deliberate duplicate fixtures.
            with zipfile.ZipFile(self.archive, "w") as archive:
                for name, data in entries:
                    if isinstance(name, zipfile.ZipInfo):
                        info = name
                    else:
                        info = zipfile.ZipInfo(name, timestamp)
                        # ZipInfo normalizes backslashes on Windows. Preserve
                        # the requested raw name for hostile-name fixtures.
                        info.filename = name
                        info.orig_filename = name
                        info.create_system = 3
                        info.compress_type = method
                        info.external_attr = ((stat.S_IFDIR | 0o755) << 16 | 0x10
                                              if name.endswith("/")
                                              else (stat.S_IFREG | 0o644) << 16)
                    archive.writestr(info, data)
        return self.archive

    def mutate_header(self, index=0, *, central=None, local=None):
        """Patch a fixture's numeric fields without reading/decompressing its data."""
        with zipfile.ZipFile(self.archive) as archive:
            central_position = archive.start_dir
            info = archive.infolist()[index]
        data = bytearray(self.archive.read_bytes())
        for _ in range(index):
            lengths = struct.unpack_from("<3H", data, central_position + 28)
            central_position += 46 + sum(lengths)
        central_fields = {"flags": (8, "H"), "method": (10, "H"),
                          "crc": (16, "I"), "compressed": (20, "I"), "size": (24, "I")}
        local_fields = {"flags": (6, "H"), "method": (8, "H"),
                        "crc": (14, "I"), "compressed": (18, "I"), "size": (22, "I")}
        for values, fields, start in ((central, central_fields, central_position),
                                      (local, local_fields, info.header_offset)):
            for field, value in (values or {}).items():
                offset, fmt = fields[field]
                struct.pack_into("<" + fmt, data, start + offset, value)
        self.archive.write_bytes(data)

    def corrupt_payload(self, index=0):
        with zipfile.ZipFile(self.archive) as archive:
            info = archive.infolist()[index]
        data = bytearray(self.archive.read_bytes())
        name_length, extra_length = struct.unpack_from("<2H", data, info.header_offset + 26)
        data[info.header_offset + 30 + name_length + extra_length] ^= 1
        self.archive.write_bytes(data)

    def assert_rejected(self):
        before = self.archive.read_bytes()
        names_before = sorted(path.name for path in self.root.iterdir())
        with self.assertRaises(SafeZipError):
            inspect_archive(self.archive)
        with self.assertRaises(SafeZipError):
            extract_archive(self.archive, self.destination)
        self.assertFalse(os.path.lexists(self.destination))
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), names_before)
        self.assertEqual(self.archive.read_bytes(), before)

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "safezip", *map(str, arguments)],
                              cwd=ROOT, capture_output=True, timeout=20)

    def test_valid_manifest_and_byte_exact_extraction(self):
        binary = bytes(range(256)) * 3 + b"\x00\xff\r\n"
        self.make_zip([("folder/", b""), ("folder/binary.bin", binary),
                       ("a file.txt", b"hello\r\n"), ("empty", b"")])
        original = self.archive.read_bytes()
        expected = {"schema": 1, "entries": [
            {"path": "a file.txt", "kind": "file", "size": 7,
             "sha256": hashlib.sha256(b"hello\r\n").hexdigest()},
            {"path": "empty", "kind": "file", "size": 0,
             "sha256": hashlib.sha256(b"").hexdigest()},
            {"path": "folder", "kind": "dir", "size": 0, "sha256": None},
            {"path": "folder/binary.bin", "kind": "file", "size": len(binary),
             "sha256": hashlib.sha256(binary).hexdigest()},
        ], "file_count": 3, "total_uncompressed_bytes": 7 + len(binary)}
        self.assertEqual(inspect_archive(self.archive), expected)
        self.assertEqual(extract_archive(self.archive, self.destination), expected)
        self.assertEqual((self.destination / "folder/binary.bin").read_bytes(), binary)
        self.assertEqual((self.destination / "a file.txt").read_bytes(), b"hello\r\n")
        self.assertEqual((self.destination / "empty").read_bytes(), b"")
        self.assertEqual(self.archive.read_bytes(), original)

    def test_stored_and_deflated_binary_and_empty_payloads(self):
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                self.make_zip([("binary", bytes(range(256))), ("empty", b""),
                               ("explicit/", b"")], method=method)
                destination = self.root / str(method)
                self.assertEqual(inspect_archive(self.archive),
                                 extract_archive(self.archive, destination))
                self.assertEqual((destination / "binary").read_bytes(), bytes(range(256)))

    def test_empty_archive(self):
        self.make_zip([])
        expected = {"schema": 1, "entries": [], "file_count": 0, "total_uncompressed_bytes": 0}
        self.assertEqual(inspect_archive(self.archive), expected)
        self.assertEqual(extract_archive(self.archive, self.destination), expected)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_cli_exact_canonical_bytes_and_agreement(self):
        self.make_zip([("z", b"last"), ("a/", b""), ("a/x", b"first")])
        original = self.archive.read_bytes()
        inspected = self.cli("inspect", self.archive)
        extracted = self.cli("extract", self.archive, "--dest", self.destination)
        self.assertEqual((inspected.returncode, extracted.returncode), (0, 0))
        self.assertEqual(inspected.stderr + extracted.stderr, b"")
        self.assertEqual(inspected.stdout, extracted.stdout)
        parsed = json.loads(inspected.stdout)
        expected = (json.dumps(parsed, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n").encode()
        self.assertEqual(inspected.stdout, expected)
        self.assertNotIn(b"\r", inspected.stdout)
        self.assertEqual(set(parsed), {"schema", "entries", "file_count", "total_uncompressed_bytes"})
        for entry in parsed["entries"]:
            self.assertEqual(set(entry), {"path", "kind", "size", "sha256"})
        self.assertEqual(self.archive.read_bytes(), original)

    def test_order_timestamp_and_compression_do_not_change_manifest(self):
        entries = [("z.txt", b"z"), ("a/", b""), ("a/b", b"b"), ("empty", b"")]
        self.make_zip(entries)
        first = manifest_bytes(inspect_archive(self.archive))
        self.make_zip(list(reversed(entries)), method=zipfile.ZIP_DEFLATED,
                      timestamp=(2030, 12, 31, 23, 59, 58))
        self.assertEqual(manifest_bytes(inspect_archive(self.archive)), first)

    def test_portable_names_and_eighty_character_boundary(self):
        names = ["a" * 80, "A-z_09.-/ leading space.txt", "COM0.txt", "COM10", "LPT10",
                 "ordinary.name", "two words/child", "trailing-hyphen-"]
        self.make_zip([(name, b"ok") for name in names])
        manifest = extract_archive(self.archive, self.destination)
        self.assertEqual([entry["path"] for entry in manifest["entries"]], sorted(names))
        for name in names:
            self.assertEqual((self.destination / name).read_bytes(), b"ok")

    def test_absolute_drive_unc_backslash_and_nonascii_names(self):
        names = ["/absolute", "//server/share/file", "C:/drive", "c:relative",
                 "\\\\server\\share", "a\\b", "back\\", "colon:name", "café", "bad\nname",
                 "a" * 81, "tab\tname", "question?", "star*", "pipe|", "quote\"", "less<"]
        for name in names:
            with self.subTest(name=name):
                self.make_zip([(name, b"")])
                self.assert_rejected()

    def test_dot_dotdot_and_empty_components(self):
        for name in ("", "/", "//", ".", "..", "./a", "../a", "a/./b", "a/../b",
                     "a//b", "a//", "a///", "a/.", "a/..", "a./b", "a /b", "a.", "a "):
            with self.subTest(name=name):
                self.make_zip([(name, b"")])
                self.assert_rejected()

    def test_reserved_device_names_including_extensions_and_case(self):
        reserved = ["CON", "PRN", "AUX", "NUL"] + [
            f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)]
        for name in reserved:
            for variant in (name, name.lower() + ".txt", "parent/" + name + ".x.y"):
                with self.subTest(name=variant):
                    self.make_zip([(variant, b"")])
                    self.assert_rejected()

    def test_embedded_nul_cannot_be_silently_truncated(self):
        self.make_zip([("abc", b"data")])
        self.archive.write_bytes(self.archive.read_bytes().replace(b"abc", b"a\x00c"))
        self.assert_rejected()

    def test_casefold_duplicates_collisions_and_prefix_conflicts_in_both_orders(self):
        pairs = [("A.txt", "a.TXT"), ("same", "same"), ("dir/", "DIR/"),
                 ("file", "FILE/"), ("parent", "PARENT/child"),
                 ("a/b", "A/B/c"), ("a", "a/b/")]
        for pair in pairs:
            for order in (pair, pair[::-1]):
                with self.subTest(order=order):
                    self.make_zip([(name, b"") for name in order])
                    self.assert_rejected()

    def test_explicit_directory_after_child_is_valid(self):
        self.make_zip([("tree/child", b"child"), ("tree/", b"")])
        self.assertEqual(inspect_archive(self.archive), extract_archive(self.archive, self.destination))
        self.assertEqual((self.destination / "tree/child").read_bytes(), b"child")

    def test_unix_special_file_types_are_rejected(self):
        for file_type in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK):
            with self.subTest(file_type=file_type):
                info = zipfile.ZipInfo("special")
                info.create_system = 3
                info.external_attr = (file_type | 0o600) << 16
                self.make_zip([(info, b"target")])
                self.assert_rejected()

    def test_unix_type_zero_and_directory_name_flag_agreement(self):
        for directory in (False, True):
            for flag in (False, True):
                for file_type in (0, stat.S_IFREG, stat.S_IFDIR):
                    with self.subTest(directory=directory, flag=flag, file_type=file_type):
                        info = zipfile.ZipInfo("item/" if directory else "item")
                        info.create_system = 3
                        info.external_attr = (file_type | 0o600) << 16 | (0x10 if flag else 0)
                        self.make_zip([(info, b"")])
                        valid = flag == directory and file_type in (
                            0, stat.S_IFDIR if directory else stat.S_IFREG)
                        if valid:
                            self.assertEqual(inspect_archive(self.archive)["entries"][0]["kind"],
                                             "dir" if directory else "file")
                        else:
                            self.assert_rejected()

    def test_directory_payload_is_rejected(self):
        self.make_zip([("directory/", b"hidden data")])
        self.assert_rejected()

    def test_encrypted_central_and_local_flags_are_rejected(self):
        for flags in (1, 0x40, 0x2000):
            for where in ("both", "central", "local"):
                with self.subTest(flags=flags, where=where):
                    self.make_zip([("secret", b"data")])
                    self.mutate_header(central={"flags": flags} if where != "local" else None,
                                       local={"flags": flags} if where != "central" else None)
                    self.assert_rejected()

    def test_unsupported_compression_is_rejected(self):
        self.make_zip([("file", b"data")])
        self.mutate_header(central={"method": 99}, local={"method": 99})
        self.assert_rejected()

    def test_entry_count_boundary(self):
        self.make_zip([(f"dir{i}/", b"") for i in range(64)])
        self.assertEqual(len(inspect_archive(self.archive)["entries"]), 64)
        self.make_zip([(f"dir{i}/", b"") for i in range(65)])
        with patch("safezip.core.zipfile.ZipFile", side_effect=AssertionError("index allocated")):
            self.assert_rejected()

    def test_lying_entry_count_is_bounded_before_zipfile_index_allocation(self):
        self.make_zip([(f"file{i}", b"") for i in range(65)])
        data = bytearray(self.archive.read_bytes())
        position = data.rfind(b"PK\x05\x06")
        struct.pack_into("<2H", data, position + 8, 1, 1)
        self.archive.write_bytes(data)
        with patch("safezip.core.zipfile.ZipFile", side_effect=AssertionError("index allocated")):
            self.assert_rejected()

    def test_file_and_total_size_exact_boundaries(self):
        payload = random.Random(23).randbytes(core.MAX_FILE_BYTES)
        self.make_zip([(f"file{i}", payload) for i in range(4)])
        manifest = extract_archive(self.archive, self.destination)
        self.assertEqual(manifest["total_uncompressed_bytes"], core.MAX_TOTAL_BYTES)
        for i in range(4):
            self.assertEqual((self.destination / f"file{i}").read_bytes(), payload)

    def test_metadata_size_quotas_are_checked_before_payloads(self):
        for entries in ([("large", b"x" * (core.MAX_FILE_BYTES + 1))],
                        [(f"f{i}", b"x" * core.MAX_FILE_BYTES) for i in range(4)] + [("extra", b"x")]):
            with self.subTest(sizes=[len(data) for _, data in entries]):
                self.make_zip(entries)
                with patch("safezip.core._payload", side_effect=AssertionError("payload was read")):
                    self.assert_rejected()

    def test_ratio_exact_boundary_and_one_byte_over(self):
        size = next(size for size in range(100, 50001, 100)
                    if size == 100 * len(zlib.compress(b"x" * size, wbits=-15)))
        self.make_zip([("at-limit", b"x" * size)], method=zipfile.ZIP_DEFLATED)
        self.assertEqual(inspect_archive(self.archive)["total_uncompressed_bytes"], size)
        self.make_zip([("over-limit", b"x" * (size + 1))], method=zipfile.ZIP_DEFLATED)
        with patch("safezip.core._payload", side_effect=AssertionError("payload was read")):
            self.assert_rejected()

    def test_positive_size_zero_compressed_size_is_rejected(self):
        self.make_zip([("impossible", b"data")], method=zipfile.ZIP_DEFLATED)
        self.mutate_header(central={"compressed": 0}, local={"compressed": 0})
        with patch("safezip.core._payload", side_effect=AssertionError("payload was read")):
            self.assert_rejected()

    def test_underdeclared_deflate_output_is_bounded_and_rejected(self):
        # A bounded 32 KiB fixture, not a huge bomb. Its real ratio is below 100;
        # forge size/CRC to describe only the first byte of the actual payload.
        payload = random.Random(2).randbytes(32768)
        self.make_zip([("dishonest", payload)], method=zipfile.ZIP_DEFLATED)
        values = {"size": 1, "crc": binascii.crc32(payload[:1])}
        self.mutate_header(central=values, local=values)
        self.assert_rejected()

    def test_crc_damage_and_late_crc_failure_clean_staging(self):
        self.make_zip([("first", b"good"), ("last", b"bad crc")])
        self.corrupt_payload(1)
        self.assert_rejected()

    def test_late_invalid_member_is_atomic_and_cannot_escape(self):
        self.make_zip([("good", b"must not be published"), ("../escaped", b"bad")])
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"untouched")
        self.assert_rejected()
        self.assertEqual(sentinel.read_bytes(), b"untouched")
        self.assertFalse((ROOT / "escaped").exists())

    def test_existing_file_empty_directory_and_nonempty_directory_preserved(self):
        self.make_zip([("payload", b"data")])
        original = self.archive.read_bytes()
        file = self.root / "existing file"
        file.write_bytes(b"original")
        empty = self.root / "empty directory"
        empty.mkdir()
        nonempty = self.root / "nonempty directory"
        nonempty.mkdir()
        (nonempty / "sentinel").write_bytes(b"original")
        for destination in (file, empty, nonempty, self.archive):
            with self.subTest(destination=destination):
                with self.assertRaises(SafeZipError):
                    extract_archive(self.archive, destination)
        self.assertEqual(file.read_bytes(), b"original")
        self.assertEqual(list(empty.iterdir()), [])
        self.assertEqual((nonempty / "sentinel").read_bytes(), b"original")
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".safezip-*")))

    def test_existing_dangling_symlink_is_preserved(self):
        self.make_zip([("file", b"data")])
        try:
            self.destination.symlink_to(self.root / "missing", target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaises(SafeZipError):
            extract_archive(self.archive, self.destination)
        self.assertTrue(self.destination.is_symlink())
        self.assertFalse(list(self.root.glob(".safezip-*")))

    def test_destination_created_during_validation_is_never_replaced(self):
        self.make_zip([("file", b"data")])
        real_commit = core._commit

        def concurrent_commit(stage, destination):
            destination.mkdir()  # Empty directory: plain POSIX rename would replace it.
            return real_commit(stage, destination)

        with patch("safezip.core._commit", side_effect=concurrent_commit):
            with self.assertRaises(SafeZipError):
                extract_archive(self.archive, self.destination)
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertFalse(list(self.root.glob(".safezip-*")))

    def test_payload_io_failure_removes_staging(self):
        self.make_zip([("first", b"good"), ("last", b"data")])
        original = core._payload

        def failing_payload(source, member, sink, total):
            if member.path == "last":
                raise OSError(errno.ENOSPC, "simulated full disk")
            return original(source, member, sink, total)

        with patch("safezip.core._payload", side_effect=failing_payload):
            self.assert_rejected()

    def test_commit_failure_removes_staging(self):
        self.make_zip([("file", b"data")])
        before = self.archive.read_bytes()
        with patch("safezip.core._commit", side_effect=OSError(errno.EACCES, "simulated denial")):
            with self.assertRaises(SafeZipError):
                extract_archive(self.archive, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".safezip-*")))
        self.assertEqual(self.archive.read_bytes(), before)

    def test_missing_destination_parent_is_not_created(self):
        self.make_zip([("file", b"data")])
        with self.assertRaises(SafeZipError):
            extract_archive(self.archive, self.root / "missing parent" / "new")
        self.assertFalse((self.root / "missing parent").exists())

    def test_inspect_is_read_only(self):
        self.make_zip([("dir/file", b"data")])
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        inspect_archive(self.archive)
        self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, before)

    def test_malformed_and_truncated_archives_are_controlled(self):
        for data in (b"", b"not a zip", b"PK\x03\x04", b"PK\x05\x06" + b"\x00" * 10):
            with self.subTest(data=data):
                self.archive.write_bytes(data)
                self.assert_rejected()

    def test_damaged_deflate_stream_is_rejected(self):
        self.make_zip([("file", bytes(range(256)) * 4)], method=zipfile.ZIP_DEFLATED)
        self.corrupt_payload()
        self.assert_rejected()

    def test_local_and_central_header_disagreement_is_rejected(self):
        for update in ({"size": 1}, {"crc": 1}, {"compressed": 1}, {"method": 8}):
            with self.subTest(update=update):
                self.make_zip([("file", b"data")])
                self.mutate_header(local=update)
                self.assert_rejected()

    def test_small_force_zip64_local_header(self):
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            with archive.open("file", "w", force_zip64=True) as sink:
                sink.write(bytes(range(256)))
        self.assertEqual(extract_archive(self.archive, self.destination)["file_count"], 1)
        self.assertEqual((self.destination / "file").read_bytes(), bytes(range(256)))

    def test_data_descriptor_archive(self):
        class Unseekable(io.BytesIO):
            def seekable(self):
                return False

            def seek(self, *args):
                raise OSError("unseekable fixture")

        buffer = Unseekable()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("file", bytes(range(256)))
        self.archive.write_bytes(buffer.getvalue())
        self.assertEqual(extract_archive(self.archive, self.destination)["file_count"], 1)
        self.assertEqual((self.destination / "file").read_bytes(), bytes(range(256)))

    def test_help_and_controlled_cli_failures(self):
        for args in (("--help",), ("inspect", "--help"), ("extract", "--help")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 0)
                self.assertIn(b"usage:", result.stdout)
        self.make_zip([("../escape", b"bad")])
        for args in (("inspect", self.archive),
                     ("extract", self.archive, "--dest", self.destination),
                     ("inspect", self.root / "missing.zip"),
                     ("inspect", self.root), (), ("unknown",),
                     ("extract", self.archive)):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertTrue(result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_readme_exact_smoke_commands_and_included_archive(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s tests -p "test*.py"', readme)
        self.assertIn("python -m safezip --help", readme)
        commands = re.findall(r"^python -m safezip (?:inspect|extract) .+$", readme, re.MULTILINE)
        self.assertEqual(len(commands), 2)
        outputs = []
        for command in commands:
            self.assertFalse(any(character in command for character in "|;&<>"))
            args = shlex.split(command)[3:]
            if args[0] == "extract":
                args[args.index("--dest") + 1] = str(self.destination)
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual((self.destination / "binary.bin").read_bytes(), bytes(range(256)))


if __name__ == "__main__":
    unittest.main()
