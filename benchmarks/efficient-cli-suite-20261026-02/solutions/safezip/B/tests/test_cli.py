import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class SafeZipCLI(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".tmp"
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="safezip tests ", dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.serial = 0

    def archive(self, members, compression=zipfile.ZIP_STORED):
        self.serial += 1
        path = self.work / f"sample {self.serial}.zip"
        with zipfile.ZipFile(path, "w", compression=compression) as output:
            for name, payload in members:
                if isinstance(name, str) and "\\" in name:
                    info = zipfile.ZipInfo(name)
                    info.filename = name
                    info.compress_type = compression
                    name = info
                output.writestr(name, payload)
        return path

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "safezip", *map(str, arguments)],
            cwd=ROOT, capture_output=True, timeout=30,
        )

    def reject(self, archive):
        original = archive.read_bytes()
        before = set(self.work.iterdir())
        destination = self.work / "new output"
        for arguments in (("inspect", archive),
                          ("extract", archive, "--dest", destination)):
            result = self.cli(*arguments)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout, b"")
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertFalse(destination.exists())
            self.assertEqual(set(self.work.iterdir()), before)
            self.assertEqual(archive.read_bytes(), original)

    def test_binary_manifest_and_extraction(self):
        payload = bytes(range(256)) * 4
        archive = self.archive([("folder/", b""), ("folder/data.bin", payload),
                                ("empty", b"")], zipfile.ZIP_DEFLATED)
        original = archive.read_bytes()
        entries = [
            {"path": "empty", "kind": "file", "size": 0,
             "sha256": hashlib.sha256(b"").hexdigest()},
            {"path": "folder", "kind": "dir", "size": 0, "sha256": None},
            {"path": "folder/data.bin", "kind": "file", "size": len(payload),
             "sha256": hashlib.sha256(payload).hexdigest()},
        ]
        expected = {"schema": 1, "entries": entries, "file_count": 2,
                    "total_uncompressed_bytes": len(payload)}
        encoded = (json.dumps(expected, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")) + "\n").encode()
        inspected = self.cli("inspect", archive)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(inspected.stdout, encoded)
        destination = self.work / "output with spaces"
        extracted = self.cli("extract", archive, "--dest", destination)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        self.assertEqual(extracted.stdout, encoded)
        self.assertEqual((destination / "folder/data.bin").read_bytes(), payload)
        self.assertEqual((destination / "empty").read_bytes(), b"")
        self.assertEqual(archive.read_bytes(), original)

    def test_order_timestamps_and_empty_archive(self):
        first = self.archive([("z", b"Z"), ("a", b"A")])
        changed = []
        for name, payload in [("a", b"A"), ("z", b"Z")]:
            info = zipfile.ZipInfo(name, (2005, 2, 3, 4, 5, 6))
            changed.append((info, payload))
        second = self.archive(changed)
        left, right = self.cli("inspect", first), self.cli("inspect", second)
        self.assertEqual((left.returncode, right.returncode), (0, 0))
        self.assertEqual(left.stdout, right.stdout)
        empty = self.archive([])
        result = self.cli("extract", empty, "--dest", self.work / "empty result")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "schema": 1, "entries": [], "file_count": 0,
            "total_uncompressed_bytes": 0})

    def test_nonportable_names(self):
        names = ["/absolute", "C:/drive", "//host/share", r"a\b", "a:b",
                 ".", "..", "a/../b", "a/./b", "a//b", "a//", "a.",
                 "a ", "CON.txt", "prn", "Aux.log", "NUL", "COM9.ext",
                 "lPt1", "é", "a" * 81]
        for name in names:
            with self.subTest(name=name):
                self.reject(self.archive([("valid", b"ok"), (name, b"bad")]))

    def test_case_and_parent_conflicts(self):
        for names in [("A", "a"), ("x", "x/"), ("x", "x/y"),
                      ("X", "x/y"), ("Dir/", "dir/")]:
            with self.subTest(names=names):
                self.reject(self.archive([(name, b"") for name in names]))

    def test_unix_special_and_mismatched_types(self):
        cases = [(stat.S_IFLNK, "link", 0), (stat.S_IFIFO, "fifo", 0),
                 (stat.S_IFSOCK, "socket", 0), (stat.S_IFCHR, "device", 0),
                 (stat.S_IFDIR, "file", 0), (stat.S_IFREG, "dir/", 16)]
        for mode, name, dos in cases:
            with self.subTest(mode=mode, name=name):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = ((mode | 0o600) << 16) | dos
                self.reject(self.archive([("first", b"ok"), (info, b"")]))

    def test_crc_failure_and_encryption_are_transactional(self):
        archive = self.archive([("first", b"ok"), ("last", b"unique CRC data")])
        data = bytearray(archive.read_bytes())
        with zipfile.ZipFile(archive) as source:
            offset = source.getinfo("last").header_offset
        name_length, extra_length = struct.unpack_from("<HH", data, offset + 26)
        data[offset + 30 + name_length + extra_length] ^= 1
        archive.write_bytes(data)
        self.reject(archive)
        encrypted = self.archive([("first", b"ok"), ("last", b"secret")])
        data = bytearray(encrypted.read_bytes())
        local, central = data.rfind(b"PK\x03\x04"), data.rfind(b"PK\x01\x02")
        data[local + 6] |= 1
        data[central + 8] |= 1
        encrypted.write_bytes(data)
        self.reject(encrypted)

    def test_quota_boundaries(self):
        for members in [[(str(i), b"") for i in range(65)],
                        [("large", b"x" * (512 * 1024 + 1))],
                        [(str(i), b"x" * (512 * 1024)) for i in range(5)]]:
            self.reject(self.archive(members))
        self.reject(self.archive([("ratio", b"x" * 100000)],
                                 zipfile.ZIP_DEFLATED))
        for members in [[(str(i), b"") for i in range(64)],
                        [(str(i), b"x" * (512 * 1024)) for i in range(4)]]:
            result = self.cli("inspect", self.archive(members))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_destinations_preserved(self):
        archive = self.archive([("payload", b"new")])
        for directory in (False, True):
            target = self.work / ("directory" if directory else "file")
            if directory:
                target.mkdir()
            sentinel = target / "sentinel" if directory else target
            sentinel.write_bytes(b"original")
            result = self.cli("extract", archive, "--dest", target)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_bytes(), b"original")
            self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
