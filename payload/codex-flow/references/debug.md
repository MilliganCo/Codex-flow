# Debug: reduce uncertainty before changing code

Record the symptom, expected behavior, reproduction input and last known working state from
available evidence. Do not infer root cause from a label such as "network", "memory" or
"permissions". Separate the application, environment, dependency/service and tooling layers.

Reproduce at the smallest relevant boundary. A failing unit/integration test, a minimal
request, or a controlled manual reproduction is preferable to immediately starting every
service. Establish whether the failure predates the current edits without destroying them.

Make a short hypothesis table in the session, not a document by default:

| Hypothesis | Evidence for/against | Smallest differentiating check |
|---|---|---|
| Most plausible mechanism | Current observed evidence | A controlled experiment |

Run one informative experiment, inspect its output, then update the hypothesis. Use at most
two independent read-only helpers when the hypotheses genuinely involve separate modules.
Do not let them make conflicting trial fixes. Avoid logging tokens, cookies, personal data
or full production responses just to collect evidence.

After two attempts reproducing the same failure with no new information, change the test
or hypothesis. Do not blindly enlarge timeout, add retries, replace dependencies or disable
checks. If an external prerequisite is missing, state the exact blocked boundary and what
was verified locally. Do not manufacture an implementation fix for an environment outage.

Once the cause is supported, make the smallest corrective change and add a regression test
when appropriate. Validate the original reproduction and neighboring failure paths. For
intermittent behavior, state the actual sample size and test conditions; several successful
runs are evidence, not proof that a race can never happen.

Use run.md's verification ladder for final integration. Report cause and supporting evidence,
changed behavior, checks run, and any unresolved uncertainty. Mark diagnosis as provisional
when reproduction or external access was not possible.
