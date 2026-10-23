# Unchanged case06 applications

[Русский](README.ru.md) · [Independent results](../README.md) · [69-file byte manifest](../source-publication.json)

These are the exact submitted files after independent assessment: A is solo 97/100,
B is updated Flow 98/100. No code was combined, repaired or adjusted after grading.
The shared guide and evaluation media were added afterward outside A/B. Both are
Python 3.12 standard-library applications; running them needs no model account,
network, API key or package installation.

From the repository root, run the Flow application:

```powershell
Push-Location benchmarks/case06/solutions/B
py -3.12 -m ascii_tree view --seed 42 --mode 4d
Pop-Location
```

Use the same commands in `solutions/A` to run solo. Keys: 1/2/3 modes, arrows camera,
[/] XW rotation, +/- zoom, Space animation, G new seed, R reset, E export,
H/? help, Q/Esc exit. The real native 57-check sequence passed for both, including
Ctrl+C 130 and terminal restoration. The documented default camera/viewport differs
between the independently generated applications.

Headless export and submitted tests from inside B:

```powershell
py -3.12 -m ascii_tree render --seed 42 --mode 4d --width 100 --height 40 --angle4d 37 --output frame.txt
py -3.12 -m unittest discover -s tests -v
```

A spells the hyperrotation flag `--angle4`, B `--angle4d`. Its own README and CLI
help are preserved. Submitted suites passed 52 tests for A and 38 for B under the
Windows SDK. Linux and visible Windows Terminal font behavior were not assessed
in this case; the separately maintained case02 examples have cross-platform CI.

`source-manifest.json` describes the local ZIP filter; `source-publication.json`
separately records all 69 files copied here, including original samples and any
submitted self-reports. Self-reports are source artifacts, not independent proof.
Native/auth state, Git pointers, HOME/temp/cache and logs were excluded before
anonymization. All original 69 hashes were verified after review and publication.
