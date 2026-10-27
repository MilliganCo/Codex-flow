Build the small integer-clamping JSON CLI specified by execution.json.

Use exactly one native worker, agent_type=worker (configured Luna medium), for
core.py. Supply its complete function contract inline. While it works, write
app.py and README.md. Save its final text as worker-proposal.txt, preserving the
one Python fenced source block; integrate that block as core.py once.
Do not write a competing core.py implementation. Do not spawn a reviewer or ask
for follow-up worker turns. The chief is the only writer. The worker uses no tools.

app.py reads a single JSON object from stdin with exactly value, min, max.
Successful output is {"value": clamp_int(value, min, max)} with exit 0. Invalid
JSON, missing/extra keys, booleans, non-integers and reversed bounds exit 2.
Use only the standard library. Support execution with python -I -B app.py;
explicitly put Path(__file__).resolve().parent on sys.path before importing core.

Do useful independent chief work immediately; batch related file writes. A small
finite CLI smoke is enough before finishing; the outer immutable acceptance gate
performs the full check after native completion. Budget status is optional.
Keep all owner contracts and verifier.py unchanged. Do not read internal native
state or prior experiments. No network, paid APIs, global edits or Git changes.
