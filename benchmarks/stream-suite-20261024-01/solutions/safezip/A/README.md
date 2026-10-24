# SafeZip 1.0

An offline Python 3.12 command-line tool using only the standard library. Run from
this directory; no installation, network access or configuration is needed.

Show the CLI and subcommand options:

```sh
python -m safezip --help
```

Inspect the included small example archive (text, binary bytes, an empty file and
an explicit directory):

```sh
python -m safezip inspect examples/sample.zip
```

Extract that archive into a new directory. `safezip-example-output` must not exist;
the destination's parent directory must already exist. Paths containing spaces
can be passed using your shell's normal quoting.

```sh
python -m safezip extract examples/sample.zip --dest safezip-example-output
```

Both commands print exactly the same compact JSON manifest followed by one LF.
The manifest has `schema: 1`, `entries`, `file_count` and
`total_uncompressed_bytes`. Entries are sorted by canonical path and contain
exactly `path`, `kind`, `size` and `sha256`. Explicit directories have no final
slash, size zero and a null digest; files report actual size and SHA-256.
Timestamps and archive entry order do not affect the manifest.

Run the standard-library test suite:

```sh
python -m unittest discover -s tests -p "test*.py"
```

Tests use temporary directories under `.tmp/` in this project and clean them up.
They cover exact manifests and payloads, names, quotas, compression, CRC,
transactional failure, destination races and controlled command-line errors.

Only stored and raw-deflated ZIP members are supported. Empty archives and empty
files are valid. The limits are 64 entries including explicit directories,
512 KiB per file, 2 MiB total uncompressed file bytes and compression ratio at most
100 per file. Empty-file ratio is 1; positive size with zero compressed size is
invalid. Metadata is checked before payload decompression. Streaming decompression
has explicit output bounds and verifies the complete stream, size and CRC, so
forged size metadata cannot cause unlimited decompression.

Names must be relative POSIX paths. Components have 1–80 ASCII letters, digits,
periods, underscores, spaces or hyphens; empty, dot and dot-dot components,
trailing periods/spaces and Windows device names (also with extensions) are
rejected. Absolute, drive, UNC, backslash and colon names are rejected. A single
final slash marks an explicit directory. Case-insensitive duplicates, file versus
directory collisions and files used as parent directories are rejected.

Encrypted members, Unix links and special file types are rejected. The directory
attribute must agree with the final slash; Unix type bits must be unspecified,
regular file or directory and agree with that kind. Directory payloads must be
empty. Archive permissions and timestamps are not applied; content is never run.

Inspection opens the source read-only and creates no output files. Extraction
validates the entire archive before writing anything, holds at most the bounded
payload total, builds a private staging directory under the destination's parent,
then atomically publishes it without replacing an existing destination. Any
validation or staging failure removes staging and leaves existing files intact.
The source archive is never modified. Errors go to stderr with a nonzero exit
status and no traceback; failed validation produces no stdout.

Atomic publication uses Windows rename, Linux `renameat2(RENAME_NOREPLACE)` or
macOS `renamex_np(RENAME_EXCL)` through the standard library. Other systems or
filesystems lacking this operation fail safely before publishing.
