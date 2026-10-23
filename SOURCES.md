# Sources and design provenance

Checked: **2026-10-13**. This is a bespoke local skill, not an official OpenAI product.
URLs below are primary documentation or the original project's source. No upstream
framework, executable or full skill source has been redistributed in this archive.
All workflow text, templates, helper code and eval cases were authored for this package.

| Source | What was used |
|---|---|
| https://developers.openai.com/codex/guides/agents-md (redirects to https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Global CODEX_HOME instruction discovery, override precedence, layered project instructions and fresh-session loading |
| https://developers.openai.com/codex/skills (redirects to https://learn.chatgpt.com/docs/build-skills) | User `.agents/skills` root, SKILL.md metadata, optional references/scripts, explicit invocation and progressive disclosure |
| https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md | Small routing entry point; supporting material kept out of the always-read body; deterministic helpers where appropriate |
| https://developers.openai.com/codex/multi-agent (redirects to https://learn.chatgpt.com/docs/agent-configuration/subagents) | Native delegation, inheritance and isolation caveats, independent read-heavy work, current optional TOML role schema |
| https://github.com/obra/superpowers/blob/main/skills/dispatching-parallel-agents/SKILL.md | Bounded independent assignments with precise ownership and reviewable outputs; not the full Superpowers workflow |
| https://learn.chatgpt.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra | Avoid large overlapping process scaffolding and indiscriminate skill loading; use a small core with conditional references |
| https://developers.openai.com/cookbook/articles/codex_exec_plans | Durable, self-contained task state for long work rather than dependence on the full chat history |
| https://learn.chatgpt.com/docs/long-running-work | Long-running tasks need outcome, constraints and verification; native task control is distinct from writing a progress note |
| https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_powershell_exe | PowerShell launch flags and per-process execution-policy argument |


## Browser-routing extension (checked 2026-10-13)

| Source | What was used |
|---|---|
| https://lightpanda.io/docs/quickstarts/skill | Official Lightpanda skill/MCP option and lack of pixel-accurate rendering |
| https://github.com/lightpanda-io/browser | Open-source CDP browser, Windows via WSL2, incomplete Web APIs, beta caveat |
| https://github.com/h4ckf0r0day/obscura | Official Rust project, Windows releases, native rendering and CDP interface |
| https://github.com/h4ckf0r0day/obscura/blob/main/docs/Use-with-Playwright.md | Browser-specific Playwright compatibility and missing tracing/storage/media features |
| https://playwright.dev/docs/api/class-browsertype | Official `connectOverCDP` significantly lower fidelity than Playwright protocol |
| https://github.com/lightpanda-io/browser/issues/3076 | First-class Playwright Test/CDP integration remains an open issue |

Claims about 9x/11x speed and Obscura memory/page-load are project benchmarks, not
confirmed improvements for this user's workloads. No engines were downloaded or
benchmarked in the ChatGPT build container. Browser selection is a non-enforcing
instruction layer and never overrides the repository's E2E browser requirements.

## Our design choices, not documented OpenAI defaults

Fast/Balanced/Thorough workflow modes; normally one writer and at most two independent
helpers; two unchanged failed attempts trigger a strategy review; checkpoints only for
long/interruption-prone tasks; `.codex-flow/PROJECT.md`; safe non-overwriting installation;
read-only bounded diagnostics; the mode names and command words.

These are hypotheses for reducing unnecessary work. They are not validated productivity
multipliers, enforced runtime quotas, official benchmark findings, or promises of a fixed
completion time. A/B behavior tests in `evals` still need live runs in the user's environment.

## User-provided basis

The supplied file was a filesystem inventory under `<user Codex configuration directory>`, not the
contents of AGENTS.md/config.toml or a runtime trace. It justified preservation of existing
files and bounded inspection. Cached filenames were not treated as proof of active plugins.
The inventory and personal configuration are intentionally NOT bundled here.

## Version-specific caveats

The local Codex custom-agent/config schema may evolve. Optional role examples reflect
the checked documentation, are not installed by default, and do not prescribe a model.
Legacy `.codex/skills` inventories do not change the currently documented user discovery
root `.agents/skills`. Other clients and execution environments require their own setup.


## Playwright default-off and upgrade safety (2026-10-13)

- https://playwright.dev/docs/best-practices — why real E2E tests check user-visible behavior and
  why they are meaningful when browser interaction itself is the acceptance criterion.
- https://playwright.dev/docs/test-projects — project-defined E2E scope/browser matrix; never
  silently skip mandatory test projects.
- https://playwright.dev/docs/api/class-testoptions — screenshot capture is configurable;
  not all tests need an unconditional screenshot pass.
- Default-off browser checks, local-change conflict rejection and the opt-in decision gate
  are this package's workflow preferences, NOT Playwright or OpenAI product defaults.
