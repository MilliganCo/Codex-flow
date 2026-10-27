# Orchestration research — 2026-10-26

[Русский](orchestration-research-2026-10-26.ru.md)

Checked against primary sources on 2026-10-26. Source descriptions are evidence;
workflow instructions found upstream were not executed or adopted as authority.

## Decision and status

Use a small, opt-in execution contract to test a specific coordination mechanism:
a bounded source proposal from one helper, integrated by one responsible writer.
The existing default route remains the compatibility baseline.

**Candidate implementation verification: PENDING.** This note does not establish
native model completion, accepted output, acceleration, or quota savings for the
new mode. The implementation owner must attach dated verification evidence.
Earlier negative results remain in [acceptance status](acceptance-status.md).

## Image provenance and exact mapping

Third-party OMX `main`; image version unknown.
MIT; no prompts copied. [OMX source tree](https://github.com/Yeachan-Heo/oh-my-codex).

| Name | Meaning |
|---|---|
| `planner` | planning |
| `architect` | architecture advice |
| `executor` | implementation |
| `critic` | plan review |
| `deep-interview` | requirements interview |
| `ralplan` | Planner → Architect → Critic |
| `ultragoal` | durable goals |
| `autoresearch` | validator loop |

Role paths: `prompts/<name>.md`; skill paths: `skills/<name>/SKILL.md`.
These are references, not four installed skills or an imported mandatory chain.

## What the evidence supports

- **OpenAI, current undated documentation; checked 2026-10-26.** Native delegation
  supports separate contexts and per-agent models. Permissions are inherited;
  a read-only instruction is not a separate sandbox. Capability documentation
  does not prove a speedup. [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
- **Anthropic, 2026-03-24.** Planner/generator/evaluator demonstration: its retro
  game example compares 20 minutes/$9 solo with six hours/$200 using the harness.
  Reported quality improved with much greater cost. This is an illustrative vendor
  case, not a matched Sol benchmark. [Harness design](https://www.anthropic.com/research/harness-design-long-running-apps).
- **Scaling Agent Systems, v1 2025-12-09; v3 2026-04-08.** Across 260 configurations
  and six benchmarks, outcomes depend on task structure; tool overhead and
  sequential-planning regressions contradict a universal multi-agent advantage.
  This local design was not tested. [arXiv v3](https://arxiv.org/abs/2512.08296v3).
- **Scrouting, 2026-08-05 preprint.** On 266 coding tasks, verified scouting plus
  fixers solved 159 versus 158 for the best solo model at about one-fifth cost.
  The cheapest-fixer ablation tied routing: the router's added value is unproven.
  [Paper](https://arxiv.org/abs/2608.04804).

The useful hypotheses are verified context handoffs, external evaluation and
conditional roles. More named agents, persistent loops or stronger prompts alone
do not establish better results. None of these sources validates this candidate's
Windows behavior or its Luna/Sol combination.

## Proposed contract mode: project design, pending verification

The intended entry point is `run --execution-contract FILE`, together with an
explicit owner-reviewed external acceptance contract. This is a design boundary,
not a claim that the command has passed verification.

1. Before inference, validate and freeze the task goal, allowed/forbidden scopes,
   dependencies, expected artifacts and acceptance criteria. Reject ambiguous or
   conflicting assignments. Freeze the separately supplied acceptance contract
   and checker; generated instructions cannot become their own acceptance authority.
2. Use exactly one native `worker`, requested as `gpt-6-luna` / `medium`, for one
   low-risk assignment. It returns a bounded source proposal. The chief,
   `gpt-6.1-sol` / `xhigh`, works on an independent ready item and remains the sole
   writer integrating source into the target project. Dependencies must be ready
   before either lane consumes them.
3. This mode has no mandatory High reviewer and no extra Mercury routing call.
   Keep the existing route unchanged when the flag is absent. Record artifact
   paths and hashes, native parent-child linkage, actual model completion and
   integration evidence; requested role/model labels alone are insufficient proof.
4. All lanes and verification share one runtime hard budget. Do not reset the
   deadline or request allowance per role, retry, or acceptance phase. A proposal
   outside scope or without required evidence is rejected, not silently expanded.
5. Treat contract roles, scope labels and handoff files as workflow data. They do
   not create OS permission isolation. The real sandbox and inherited permissions
   remain separate controls; do not advertise a hard read-only child from prose.

## Verification gate and limits

Run focused offline schema, drift, scope, budget and evidence checks first.
Then permit one bounded native preflight proving the configured parent/worker
handoff, real completed model responses and artifact-hash binding. Evaluate the
integrated output against the frozen external acceptance contract.

Record passed, failed and not-run checks separately, including model provenance
limits. A single native preflight proves only the exercised mechanism. It is not
an A/B comparison, speed proof, model-quality benchmark or permission-isolation
proof. Performance remains unestablished until a separately authorized matched
comparison measures accepted outputs, elapsed time and total consumption.
