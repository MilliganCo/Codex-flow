# Reduce orchestration stages before compressing transport

The original fixed cohort remains negative: Flow needed 19 versus 13 requests on
LedgerReconcile and 28 versus 17 on SafeZip, despite all four scores being 100.
The subsequent Tree confirmation is also retained: one Solo timeout prevents its
quality advantage for Flow from establishing successful-completion acceleration.

## Observations and decision

Exact owned Ledger rollout inspection identifies one late status-only stage;
another initially suspected stage was actually batched with tests. SafeZip batched
all five status calls with commands. Its chief nevertheless took five preparatory
shell stages before the first patch, while its child performed three inventory
reads and later a follow-up read. A status RPC itself was short; model round trips
and duplicated preparation are not free. These observations do not establish the
counterfactual saving or explain the entire gap.
The Flow policy also repeated reviewer, waiting, checkpoints and time-planning
instructions in CLI, command assembly and process launch.

Keep one chief as writer and one initial context-only reviewer/high. Remove the
first-tool ordering barrier: start the review promptly alongside useful work, and
receive its evidence before acceptance. A missing or unused helper remains degraded.
For bounded work prefer one cohesive production/tests/examples/README slice and a
finite batch of acceptance checks. Split at actual dependencies, errors or unknowns.
Do not impose a separate early smoke or budget checkpoint merely to satisfy process.
Required platform startup/control/shutdown, boundary tests and actual artifacts
remain necessary. Status is optional decision support, not optional budget enforcement.

The owned policy has one stable contract plus a short dynamic limit/tool suffix.
This removes repeated instructions; it does not summarize user tasks or SDK history.
Changing scheduling advice is a behavioral experiment, **not lossless compression**.

## GZip boundary

GZip/DEFLATE removes byte redundancy through a sliding-window reference dictionary
and coding. HTTP content coding changes the representation of transferred bytes;
it does not remove the decoded model context. The current gateway intentionally
requires identity encoding, and support for compression on the private native
backend has not been established. Keep its transport, request bytes, parser,
authentication, terminal semantics and retries unchanged.

Use the narrower idea of eliminating duplication in our own policy and avoiding
re-reading unchanged evidence. Do not send compressed/base64 tasks to the model,
discard acceptance text, compact native history, add cross-arm caches or treat a
smaller byte count as measured token, quota or latency savings.

References: [GZip format](https://www.rfc-editor.org/rfc/rfc1952.html),
[HTTP content coding](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.4),
[token accounting](https://help.openai.com/en/articles/4936856-understanding-and-counting-tokens)
and [stable prompt prefixes](https://developers.openai.com/api/docs/guides/prompt-caching).
The observed Flow contract shrank from 4543 to 2806 UTF-8 bytes; this is a byte
measurement, not a tokenizer or quota measurement.

## Prospective verification

A fresh two-task cohort repeats the literal LedgerReconcile and SafeZip tasks,
graders and strict 100/100 rules. Both Sol XHigh roots retain 1500 seconds and 80
shared native requests per arm; one parallel A/B pair per task, pairs sequential.
All outcomes are retained. No solution repair, unchanged retry, replacement of old
results or adaptive task selection is permitted. Success requires both arms to
complete and pass unchanged-source independent evaluation, no quality loss, and
at least a 1.10 successful-time ratio on **each** task. One pair per task remains
a case study, not proof of universal or statistical superiority.

The verified pre-change development bundle is
`before-cohesive-policy-20261024.bundle`, pointing to `eef56871728021e0d09ae0fdb5cbebc3854bea8f`.
No global installed skill, settings, protected Harness lab or paid API is changed.

## Preflight discovery: Windows budget publication

The first new native prerequisite stopped during the owner's connection problem;
it remains an immutable failed record. A fresh preflight after that external-state
change completed all six model requests, the real high-profile child, three MCP
calls and the sandboxed function check, but retained `publisher_failed=true`.
The old boolean did not capture its exception, so that precise historical failure
cannot be retrospectively assigned an OS error code.

A separate pure metadata reproduction on this Windows volume shows an ordinary
open reader can block atomic replacement with WinError 5. The previous valid JSON
survives; replacement succeeds after closing the reader. A tested share-delete
reader did not solve the actual filesystem behavior and was not retained.

Keep atomic replacement and unchanged reader/security boundaries. For this owned
metadata publication only, retry Windows PermissionError 5/32 at most three times
after 10/20/40 ms. Record all error attempts, recovered and failed publications and
last numeric errno/winerror; never log exception messages or paths. Validation,
other I/O and inference are not retried. An exhausted/nonretryable publication or
failed publisher shutdown keeps the failure flag sticky, even after later success.
The stop event interrupts waits; the original hard execution budgets remain intact.
Fresh native verification must still pass before benchmarking. The extra setup
attempts are retained separately and earn no benchmark credit.

See [Windows file sharing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
and [atomic replacement](https://docs.python.org/3.12/library/os.html#os.replace).
