# Local verification

Platform: Windows, Python 3.12.10. No network or third-party packages were used.
The implementation, tests, README, and example are all inside this workspace.

## Reproduce

```console
python -m unittest discover -s tests -p "test*.py"
```

Final run: 35 tests, 34 passed, 1 skipped, 0 failures. The skipped test attempts
to create a dangling destination symlink; this Windows account lacks permission
to create symlinks. Unix symlink ZIP entries are independently tested and rejected.
The saved output is in `verification/unittest.txt`.

```console
python -m safezip --help
```

```console
python -m safezip inspect examples/sample.zip
```

```console
python -m safezip extract examples/sample.zip --dest sample-output
```

Actual CLI smoke runs passed with a fresh owned destination containing spaces.
Inspect and extract stdout matched byte for byte, including a single LF and no
CR. The sample's binary payload and original archive bytes were checked. The
expected sample manifest is saved in `examples/sample.manifest.json`.

## Acceptance checks 1–5

1. Basic inspect: `test_exact_manifest_stdout_and_command_agreement` checks the
   entire expected manifest and exact serialized bytes through the real CLI.
2. Byte-exact extraction: `test_valid_stored_and_deflated_binary_bytes` and
   `test_multichunk_deflate_stream` compare complete extracted file bytes.
3. Inspect/extract agreement: both the CLI manifest test and README smoke compare
   successful stdout bytes.
4. Order/mtime determinism: `test_order_and_timestamp_determinism` reverses entry
   order and changes all entry timestamps.
5. Portable names: `test_portable_names_and_80_character_boundary` checks valid
   names, spaces, implicit parents, and the inclusive component limit.

## Acceptance checks 6–10

6. Absolute/drive/UNC/backslash rejection: `test_nonportable_names` includes each
   form, preserving raw backslashes in on-disk ZIP fixtures on Windows.
7. Dot/dotdot/empty components: the same test checks these and repeated slashes;
   `test_nul_in_original_name` also checks names truncated by `ZipInfo.filename`.
8. Casefold duplicates/prefix conflicts: `test_duplicates_and_file_parent_conflicts_in_both_orders`
   checks both entry orders, file/directory collisions, and differently cased parents.
9. Special files: `test_special_file_types` and
   `test_type_bits_and_directory_flag_agreement` check all special Unix types and
   inconsistent regular/directory/unspecified type metadata.
10. Encryption: `test_encryption_flags_rejected_before_payload` checks ordinary,
    strong-encryption, and masked-header flags without invoking decompression.

## Acceptance checks 11–15

11. Quotas/boundaries: inclusive entry, file-size, total-size, and ratio tests;
    metadata-before-decoder checks; forged 4 MiB deflate output with declared size
    1 is stopped after producing only 2 bytes per inspection/extraction attempt.
12. CRC: `test_crc_corruption_and_late_failure_cleanup` corrupts a late payload;
    `test_streaming_data_descriptors_and_crc` also corrupts descriptor CRCs.
13. Late invalid-member atomicity: `test_late_invalid_member_does_not_write_anything`
    checks valid early content followed by a traversal name.
14. Existing destination preservation: file, empty directory, and populated
    directory tests; a real Windows no-replace rename test simulates a concurrent
    empty-directory creator after the advisory existence check.
15. Failure cleanup/no outside writes: rejection tests compare the destination
    parent's complete before/after file set. Injected write/commit failures check
    staging cleanup; a late CRC failure preserves an unrelated sentinel.

## Acceptance checks 16–20

16. Unchanged archive: rejection helpers and successful byte-extraction/README
    tests compare the complete source archive before and after commands.
17. Empty/binary payloads: empty archives, empty files, directories, all 256 byte
    values, NUL, CR/LF, and multichunk payloads are covered.
18. Help/space paths/controlled exits: real CLI tests cover help for all commands,
    missing arguments/files, malformed ZIPs, and archive/destination/member spaces.
19. Authored tests: 35 standard-library unittest methods in `tests/test_safezip.py`.
20. Working README smoke: `test_readme_commands_and_included_archive` executes
    the documented flags and included `examples/sample.zip` with a fresh destination.

## Additional evidence and limits

A deterministic finite probe mutated 300 small ZIP archives. There were 278
`SafeZipError` rejections, 6 zlib errors, 4 unsupported-version rejections, and 12
still-valid mutations. Fifteen actual CLI probes produced no traceback. This is
additional malformed-input evidence, not exhaustive fuzzing.

An independent read-only review checked local payload offsets and bounded
decompression. Follow-up executable tests cover data descriptors, small ZIP64
central/local records, deflate truncation, and trailing compressed bytes.

Actual platform checks exercised Windows startup, extraction, cleanup, and
no-replace commit. Linux/macOS native commit paths were not run here. Injected
I/O failures and race timing are simulations; the rename operation itself uses
the real Windows filesystem. Concurrent mutation of source files or destination
ancestors is outside the documented operating boundary. These local checks do
not claim an independent evaluator score.
