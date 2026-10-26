# SafeZip v1.0 — common A/B task

Build a complete offline Python 3.12 standard-library CLI, source, tests and README.
No network, external dependencies, API keys, paid APIs or other workspace access.

```
python -m safezip --help
python -m safezip inspect sample.zip
python -m safezip extract sample.zip --dest NEW_DIRECTORY
```

Support stored/deflated ZIP with regular files and explicit directories; preserve
binary bytes and the input archive. Empty archives are valid. Reject encrypted,
Unix symlink/special-file entries and damaged CRC. Unspecified Unix file-type bits
(0) are ordinary only when the ZIP directory flag/name agrees; regular-file and
directory type bits must agree with file/directory kind. Do not execute archive content.

Portable member names are relative POSIX paths. Each component is 1..80 ASCII
characters from letters/digits/`._ -`, with no empty, . or .. component, trailing dot
or space, colon or backslash. Reject absolute, drive and UNC paths. Reject reserved
CON,PRN,AUX,NUL,COM1..COM9,LPT1..LPT9 case-insensitively, including extension forms.
Reject case-insensitive duplicates, file/directory collisions and a file used as a
parent directory. One final slash denotes an explicit directory and is removed
from canonical manifest path; it does not permit empty internal components.

At most 64 entries (files and directories), each file <=512 KiB, total uncompressed
file bytes <=2 MiB, compression ratio <=100. Empty-file ratio is 1; positive size
with zero compressed size is invalid. Enforce metadata bounds before decompression
and actual bytes read. Never allocate/decompress an actual huge archive bomb.

inspect is read-only; extract accepts only an absent destination. Validate the
whole archive, use staging under destination parent, and commit only a complete
result. A failure leaves destination absent, existing files untouched and no staging.
Never replace an existing destination file/directory. Errors are controlled nonzero,
not raw tracebacks. Source archive is unchanged on success and failure.

Both successful commands print exactly the same canonical manifest for the same
archive, with no extra stdout: schema=1, entries array, file_count and
total_uncompressed_bytes. Every entry has exactly path,kind,size,sha256; kind is
file or dir; explicit dir size=0 and sha256=null. Files use actual uncompressed
size and SHA256. Sort entries by canonical path. JSON bytes are exactly
`json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'`.
Reordering entries or changing their timestamps preserves that manifest for the
same set of entries/payload. File count excludes directories; byte total sums files.

Include >=5 runnable standard-library unittest tests in tests/, including valid
archives, rejection and transactional behavior. README must document the actual
command `python -m unittest discover -s tests -p "test*.py"` and --help. Include a
small valid example archive and real single-line fenced smoke commands:
`python -m safezip inspect <included-relative-archive>` and
`python -m safezip extract <included-relative-archive> --dest <new-directory>`.
No pipelines, shell operators or installer in these commands. The evaluator reruns
the actual flags/example archive, changing only destination to an owned fresh path;
it checks commands and outputs, not README wordcount.

Acceptance uses 20 independently assessed criteria, each 5 points: basic inspect;
byte-exact extraction; inspect/extract agreement; order/mtime determinism; portable
names; absolute/drive/UNC/backslash rejection; dot/dotdot/empty-component rejection;
casefold duplicates/prefix conflicts; special files; encryption; quotas/boundaries;
CRC; late invalid member atomicity; existing destination preservation; failure
cleanup/no outside writes; unchanged archive; empty/binary payloads; help/space paths/
controlled exits; >=5 authored tests; working README smoke. All 20 must pass
(100/100), sources unchanged. Partial results remain partial. Work independently.
