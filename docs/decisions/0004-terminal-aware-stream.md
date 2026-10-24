# Finish HTTP inference at the validated model terminal

The exact case08 exception was not retained. Its HTTP200/header success followed
by a failed body read cannot identify a provider, network, TLS or timeout cause.
That immutable failure is not retroactively relabeled.

A separate real loopback HTTP reproduction establishes a gateway defect:
one proper chunk contains a complete `response.completed`, but the transport
remains open or omits its final zero chunk. The old whole-body reader returns502
(1.515 seconds with the held-open fixture). The corrected reader returns200 in
0.016 seconds, with exactly one upstream request and no inference/external network.
This is a transport fixture result, not a model-generation speedup.

The retained [old/new loopback receipt](../evidence/terminal-stream-loopback.json)
records both held-open and immediately truncated HTTP framing conditions, their
source fingerprints and one upstream open per call. Sub-tick durations in that
receipt reflect the Windows timer's 15.625 ms resolution and are not zero latency.

## Decision

Read bounded blocks with `read1`, parse real SSE event boundaries incrementally,
and buffer downstream output until a complete, validated model terminal exists.
Preserve original bytes through that terminal. Never wait for an HTTP tail after
logical completion; reject contradictory complete terminals already received.
An interrupted/truncated terminal, `failed`, `incomplete`, `error`, item completion
or `[DONE]` alone is not success. Usage comes only from the actual terminal.

After verified model completion, cleanup errors are separate diagnostics and do
not retract the model result. This supersedes the case08 blanket close-error
failure rule. Before completion, failures remain failures with unknown usage.
There are no retries, replay, provider changes or additional request attempts.
Completion status describes the model terminal, not a downstream receiver ACK.

Bounds, fixed routes/auth handling, request bytes, deadline/cancel, disabled input
injection and sandbox permissions remain intact. Record bytes received, terminal
observation, read termination, EOF observation and typed cleanup/read errors;
never log response contents, auth or exception messages.

The [Responses streaming reference](https://developers.openai.com/api/reference/resources/responses/streaming-events)
identifies `response.completed` as model completion. The
[ChatGPT plan inference guide](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
requires handling completed, failed, incomplete and interrupted results separately.
These references support terminal semantics; they do not authorize changing the
native CLI's endpoint or reading/copying its credentials. WebSocket steering is
outside this HTTP-only gateway, which refuses Upgrade.

## Balanced orchestration and evaluation

Readonly workers may return a bounded implementation proposal in their final
reply for a stable, independent module API while the chief works on another part.
Workers never write files or delegate; the chief remains the sole application-file
writer, reviews the proposal, integrates once and tests the production result.
Proposal generation/review remains inside the same per-arm time/request limits.

The fixed follow-up series is canonical Tree plus LedgerReconcile and SafeZip.
Tree keeps its original prompt, evaluator, rubric and native57-check protocol.
New tasks freeze public contracts and deterministic hidden fixtures before any
generation. All outcomes are retained; no retry-until-win or best-run selection.
Performance requires normal completion and independent acceptance of both arms;
quality and each task's timings remain visible beside any aggregate.
