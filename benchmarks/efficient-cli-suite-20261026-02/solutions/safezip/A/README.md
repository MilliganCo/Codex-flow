# SafeZip 1.0

Offline ZIP inspection and transactional extraction using Python 3.12 and only
the standard library. Run commands from this repository directory. No installation,
network access, credentials, or third-party packages are needed. Archive contents
are treated as data and are never executed.

Show the commands and flags:

```text
python -m safezip --help
```

Inspect the included small archive (text, binary bytes, an empty file, and an
explicit directory):

```text
python -m safezip inspect examples/sample.zip
```

Extract it into a new directory. `sample-output` must not exist; its parent must
already be a directory. Choose a fresh destination for another extraction.

```text
python -m safezip extract examples/sample.zip --dest sample-output
```

Quote archive and destination arguments containing spaces. Both commands validate
the entire archive and print exactly one identical canonical JSON manifest on
success, followed by a single LF byte. The archive is opened read-only. Errors go
to stderr with a nonzero exit status and no traceback; failed validation prints
no manifest. `inspect` creates no output directory. Empty archives are valid.

The manifest has `schema=1`, `entries`, `file_count`, and
`total_uncompressed_bytes`. Entries are sorted by canonical path, with exactly
`path`, `kind`, `size`, and `sha256`. Explicit directories have kind `dir`, size
zero, and a null digest; their final slash is omitted. Implicit parent directories
are created as needed but are not additional manifest entries. Files use actual
uncompressed sizes and lowercase SHA256 digests. File counts and byte totals
exclude directories. Entry order, timestamps, and compression method do not affect
the manifest for identical paths and payloads. Serialization is precisely
`json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'`,
encoded as UTF-8.

Only stored and raw-deflated ZIP members are supported. Encryption, Unix symlinks,
special files, CRC damage, malformed headers, multi-disk archives, and unsupported
compression methods are rejected. Directory names, DOS directory flags, and any
Unix regular-file/directory type bits must agree. Zero Unix file-type bits are
accepted when the directory flag and name agree. Directory payloads must be empty.

Member paths are relative POSIX names. Every component has 1–80 ASCII letters,
digits, dots, underscores, spaces, or hyphens. Empty, `.` and `..` components,
trailing dots/spaces, colons, backslashes, absolute paths, drive paths, UNC paths,
and Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`,
including extension forms and any letter case) are rejected. A single final slash
marks an explicit directory. Duplicate paths and file/directory conflicts are
checked case-insensitively, including files used as ancestor directories.

Limits are inclusive: 64 explicit entries, 512 KiB per file, 2 MiB total file
bytes, and an uncompressed-to-compressed ratio of 100. Empty-file ratio is 1;
positive uncompressed size with zero compressed size is invalid. Central-directory
entry counts are bounded before index allocation. Metadata quotas are checked
before decompression; decoding uses bounded chunks and rejects actual output
beyond the declared size or quotas, rather than trusting advertised sizes.

Extraction validates all metadata before creating a private staging directory
under the destination parent. All payloads, sizes, hashes, and CRCs are validated
there before publishing the complete directory with an atomic no-replace rename.
Existing files, directories, and symlinks are refused, including a destination
created during extraction. Failures remove staging and leave the destination
absent (or preserve a destination created by another process). Original member
permissions and timestamps are not restored. Target filesystem path-length and
permission limits still apply and produce controlled errors.

Atomic publication uses Windows rename, Linux `renameat2(RENAME_NOREPLACE)`, or
macOS `renamex_np(RENAME_EXCL)`, through standard-library facilities. Platforms
or filesystems lacking atomic exclusive rename fail safely without publishing.

Run the offline regression tests:

```text
python -m unittest discover -s tests -p "test*.py"
```

Tests cover successful CLI output, binary extraction, determinism, names and type
rules, encryption, quota boundaries, dishonest size metadata, CRC corruption,
transaction failures, destination races, source preservation, and these exact
README smoke commands. Test scratch directories are created and removed inside
this repository. Symlink-specific testing skips when the OS denies symlink creation.
