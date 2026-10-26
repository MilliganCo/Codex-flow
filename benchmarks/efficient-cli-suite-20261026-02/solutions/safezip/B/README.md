# SafeZip 1.0

An offline Python 3.12 standard-library CLI for inspecting and safely extracting
stored or deflated ZIP archives. No installation, dependencies, network or keys
are needed. Run commands from this directory.

```console
python -m safezip --help
```

Inspect the included small archive (a directory, text, binary bytes and an empty file):

```console
python -m safezip inspect examples/sample.zip
```

Extract into a **new** directory whose parent already exists:

```console
python -m safezip extract examples/sample.zip --dest sample-output
```

Choose another absent destination on subsequent runs. Quote archive/destination
paths containing spaces. Both commands emit only the same canonical JSON manifest
on stdout: schema 1, sorted `entries`, `file_count` and `total_uncompressed_bytes`.
Each entry has `path`, `kind`, `size`, `sha256`; explicit directories have size 0
and a null hash. Implicit parent directories are created but are not manifest
entries. Files use their actual byte length and SHA256. JSON has sorted keys,
no extra whitespace, UTF-8 encoding and exactly one final LF. Archive ordering,
compression choice and timestamps do not affect the manifest.

Run all tests:

```console
python -m unittest discover -s tests -p "test*.py"
```

Member names must be relative POSIX paths. Each component contains 1–80 ASCII
letters, digits, dots, underscores, spaces or hyphens. Empty, `.` and `..`
components, trailing dots/spaces, Windows device names (including extension
forms), absolute paths, drive/UNC paths, colons and backslashes are rejected.
One final slash marks an explicit directory. Directory names and ZIP directory
attributes must agree. Unix type bits must be unspecified, regular-file or
directory and must agree with the entry kind. Symlinks, special files, encryption,
other compression methods, case-insensitive duplicates, file/directory collisions
and files used as parent directories are rejected.

Limits include directories in the maximum 64 entries. Each file is at most
512 KiB, file bytes total at most 2 MiB, and each file's uncompressed/compressed
ratio is at most 100. An empty file's ratio is 1; positive size with zero compressed
bytes is invalid. Metadata is bounded before decompression. Payloads are streamed
through bounded reads, verified against actual sizes and CRC, and hashed.
Malformed streams and hidden payload bytes beyond declared sizes are rejected.
Empty archives and arbitrary binary file bytes are supported.

`inspect` only reads the input. `extract` validates the complete archive before
creating a private staging directory under the destination parent, writes the
verified bytes, then publishes the complete tree with an atomic rename that
refuses an existing target. A validation or extraction failure leaves no
destination or staging directory and preserves pre-existing files. An existing
destination, including an empty directory, file or dangling symlink, is rejected.
Archive contents are never executed, and the source archive is never modified.
Errors go to stderr with a nonzero exit and no traceback; usage errors exit 2.

Atomic publication uses Windows' no-replace rename, Linux `renameat2` with
`RENAME_NOREPLACE`, or macOS `renamex_np` with `RENAME_EXCL`. Other platforms or
filesystems without the required atomic primitive fail safely. File permissions
and timestamps are not restored. Multipart ZIPs and trailing data after the ZIP
comment are unsupported; small ZIP64 and streaming data-descriptor ZIPs work.
