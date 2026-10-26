# SafeZip v1.0

Offline ZIP inspection and transactional extraction using Python 3.12 and only
the standard library. Run from this project directory; no installation is needed.
Archive content is treated as data and never executed.

Get command and option help:

```text
python -m safezip --help
```

Inspect the included small example archive:

```text
python -m safezip inspect examples/sample.zip
```

Extract it into a new directory (the destination must not already exist):

```text
python -m safezip extract examples/sample.zip --dest sample-output
```

The example contains `hello.txt`, `assets/`, `assets/bytes.bin` (all 256 byte
values), and `empty.txt`. Both commands print the same single line of canonical
UTF-8 JSON ending with LF. Success exits 0; errors exit nonzero with a message on
stderr and no manifest on stdout. Quote archive and destination paths containing
spaces. Subcommand help is available with `inspect --help` and `extract --help`.

The manifest has `schema:1`, `entries`, `file_count`, and
`total_uncompressed_bytes`. Entries are sorted by canonical path and contain
exactly `path`, `kind`, `size`, and `sha256`. An explicit directory loses its final
slash and has size 0 and SHA256 null. Implicit parent directories are created
during extraction but do not add manifest entries. File hashes and sizes describe
the actual uncompressed bytes. Archive ordering, timestamps, and compression
choices do not affect the manifest for the same entries and payloads.

Names must be relative POSIX paths. Components contain 1–80 ASCII letters, digits,
or `._ -`; empty components, `.`/`..`, trailing dots/spaces, Windows device names
(including extension forms), colons, backslashes, and absolute/drive/UNC paths are
rejected. Case-insensitive duplicates, file/directory collisions, and files used
as parents are rejected. Unix file types and directory indicators are checked;
unspecified Unix type bits require the DOS directory flag and name to agree.
Symlinks, special files, encrypted entries, and compression methods other than
stored/deflated are rejected. Empty archives and empty/binary files are supported.

Limits are inclusive: 64 entries counting explicit directories, 512 KiB per file,
2 MiB total file bytes, and compression ratio 100 per file. Empty-file ratio is 1;
positive size with zero compressed bytes is invalid. Metadata and the central
directory are bounded before payload decompression. Streaming decompression also
bounds actual output, verifies exact sizes and CRC32, and computes SHA256. A
forged small size cannot hide a large deflate stream. Multi-disk ZIPs and malformed
records are rejected; ordinary and fixed ZIP64 end records are supported.

Inspection opens the archive read-only and creates no output tree. Extraction
requires an absent destination and an existing parent directory. It validates all
metadata, writes into private `.safezip-*` staging under that parent, verifies all
payloads, and atomically publishes only a complete tree. Handled failures remove
staging. Existing destinations, including empty directories and dangling
symlinks, are preserved. The source archive is opened read-only for both commands.
Permissions and timestamps from ZIP metadata are not applied to extracted files.

Atomic publication refuses a destination that appears during extraction. Windows
uses its no-replace directory rename; Linux uses `renameat2(RENAME_NOREPLACE)` and
macOS uses `renamex_np(RENAME_EXCL)`, accessed through standard-library `ctypes`.
Extraction fails safely if the platform/filesystem lacks this operation.
Inspection is portable across Python 3.12 platforms. Transactions cover handled
errors; abrupt process termination or power loss may leave staging, and the tool
does not claim power-loss durability or protection from a hostile process with
write access to the destination parent.

Run the offline standard-library test suite:

```text
python -m unittest discover -s tests -p "test*.py"
```

Tests cover exact output and extraction, both compression methods, empty/binary
data, determinism, name/type/encryption rejection, limits, forged deflate output,
CRC failures, transaction cleanup, destination races, controlled CLI errors, ZIP64,
and these README commands. Temporary test data stays in the project’s `.tmp/`.
