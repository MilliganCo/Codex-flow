"""Rebuild sample.zip deterministically using only the standard library."""

from pathlib import Path
import stat
import zipfile


def main():
    target = Path(__file__).with_name("sample.zip")
    members = [("demo/", b""), ("demo/hello.txt", b"Hello from SafeZip!\n"),
               ("demo/bytes.bin", bytes(range(256))), ("empty.txt", b"")]
    with zipfile.ZipFile(target, "w") as archive:
        for name, payload in members:
            info = zipfile.ZipInfo(name, (2024, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            directory = name.endswith("/")
            mode = stat.S_IFDIR | 0o755 if directory else stat.S_IFREG | 0o644
            info.external_attr = (mode << 16) | (0x10 if directory else 0)
            archive.writestr(info, payload)


if __name__ == "__main__":
    main()
