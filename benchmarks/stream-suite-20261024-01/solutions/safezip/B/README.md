# SafeZip 1.0

An offline Python 3.12 CLI using only the standard library. Run commands from this
repository; no installation or network access is needed.

```console
python -m safezip --help
```

Inspect the included example (a directory, a text file, an empty file, and binary data):

```console
python -m safezip inspect examples/sample.zip
```

Extract into a destination that does not exist yet:

```console
python -m safezip extract examples/sample.zip --dest sample-output
```

Both successful commands write only the same canonical JSON manifest followed by
one LF. Entries are sorted by canonical path. Explicit directories have size zero
and a null SHA256; files report actual byte counts and SHA256 hashes. Implicit
parent directories are created during extraction but are absent from the manifest.
Archive ordering and timestamps do not affect the output. The source is opened
read-only. Content is never executed, and archive permissions are not applied.

Names must be relative POSIX paths with 1–80 ASCII characters per component from
letters, digits, `.`, `_`, space, and `-`. Empty components, `.`/`..`, trailing dots
or spaces, Windows reserved device names (including extension forms), absolute
paths, backslashes, and colons are rejected. One final slash denotes an explicit
directory. Case-insensitive duplicates, file/directory collisions, and files used
as parents are rejected. Unix special files, encryption, unsupported flags and
compression methods, malformed metadata, and incorrect CRCs are rejected.

Limits include directories in the maximum of 64 entries. Each file is at most
512 KiB; total file bytes are at most 2 MiB; each member's uncompressed/compressed
ratio is at most 100. Empty payloads have ratio 1; nonempty payloads cannot have
zero compressed size. Metadata is checked before decompression. Streaming also
checks actual sizes and CRCs with bounded buffers, including deflate streams whose
declared size is forged. Empty archives are supported.

Extraction requires an existing parent directory that is not a symlink or junction.
It writes to a private `.safezip-` staging directory inside that parent, validates
every member, then atomically renames the completed tree without replacing any
existing destination. On failure, staging is removed and the destination remains
absent. Existing destinations, including dangling links, are rejected. Do not
concurrently modify the source archive or destination ancestors while a command
runs. Windows uses its no-replace rename; Linux/macOS use their no-replace rename
primitives through standard-library `ctypes`. Other platforms fail closed if no
such primitive is available. Single-disk ZIP64 records and local headers are
supported within the same quotas; multi-disk archives and ZIP64 end-record
extensions are unsupported. Streaming data descriptors are checked as well.

Paths containing spaces work when quoted. Errors go to stderr with a nonzero exit
status and no traceback; successful JSON is UTF-8, compact, and deterministic.

Run the authored standard-library tests:

```console
python -m unittest discover -s tests -p "test*.py"
```
