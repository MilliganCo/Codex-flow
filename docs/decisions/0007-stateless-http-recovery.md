# Recover one transient HTTP failure inside the original budget

The first cohesive-work cohort did not finish: Ledger A stopped after eight
complete responses and an upstream body timeout; B stopped after one complete
response and a connection reset while opening the next request. Both runs and
their partial artifacts remain failed. ZIP is retained as not run after this
infrastructure failure; the denominator is not reduced. No elapsed-time ratio
from these failed branches is a speed result.

## Opt-in boundary

`native_request_retries` is a project-local integer, default 0 and maximum 1.
The native provider receives this as `request_max_retries`; `stream_max_retries`
remains 0. No global settings, auth, model, request bytes or sandbox change.
For a fresh comparison enable the same setting for **both** arms. Every new
upstream attempt reserves the original shared request budget and shares its
monotonic deadline; retry delays are included in the measured elapsed time.

Recovery-mode admission requires explicit `store:false`, an input array and no
`previous_response_id`, `conversation` or `background` key. Reject incompatible
inputs before reservation/forwarding. This also covers native retries following
a local disconnect without an HTTP response. Budget-message input mutation and
recovery cannot be combined.

The gateway buffers the model stream through a validated terminal before delivery.
Only typed timeout/reset/aborted/incomplete-read failures during upstream open or
body read, and upstream HTTP 500/502/503/504, receive a retryable 503. Typed wrapped
URL errors are inspected by type, never by exception text. Validation, quota,
TLS/unknown I/O, controls and failed/incomplete model terminals are nonretryable.
In recovery mode an upstream 401 is represented as a local 403 to avoid triggering
native auth-refresh recovery; the original status remains in diagnostics.
Default-mode status mapping is preserved. Valid completion followed by cleanup
failure remains successful and never gains a retryable error.

The gateway never replays requests itself. Native HTTP recovery is separately
verified with the pinned CLI on a synthetic local stream, including denials and
budget exhaustion. A per-run HMAC fingerprint establishes equal payload bytes,
not backend idempotency. The first model generation may continue after a lost
connection and may consume quota: retain its unknown usage as null and count
both physical attempts. Do not claim exactly-once generation, free retries,
subscription savings or acceleration from this infrastructure change alone.

## Evaluation isolation on Windows

Precreating and denying a future evaluation parent left a persistent sandbox-user
deny on this Windows host, blocking the evaluator before it started. Preserve
those startup-failure receipts. A new sibling evaluation environment created only
after both generation processes ended ran the unchanged evaluator and source
copies successfully, without editing ACLs or disabling the sandbox. Prepare fresh
evaluation siblings after each pair; before the next pair, deny all existing owned
sibling directories identically for both arms. Native auth/history and current-peer
physical read isolation limitations remain explicitly degraded.

## Verification and prospective cohort

Unit/loopback contracts cover admission, exact payload preservation, physical
reservations, deadline/cap refusal, typed classification and no partial delivery.
The pinned native CLI must additionally demonstrate one resend for a synthetic
503 and none for authentication, terminal failure and exhausted cap, without real
model generation. Freeze a new runtime and preregistration before a new real cohort.
Keep the original literal tasks, 20 criteria, strict 100/100, 1500 seconds and 80
physical attempts per arm. Both accepted arms must finish normally, and Flow must
reach a successful-time ratio of at least 1.10 on each task with no quality loss.
All old failures remain separate, without pooling or replacement.

[Native retry configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[HTTP retry semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2).
