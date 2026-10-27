# Model roles and evidence

[Русский](model-roles.ru.md)

Checked: **2026-10-27**. The catalog describes existing wiring and documented
candidates. Reading it never starts a model, tests an account, or changes routing.

```powershell
python codex-flow.py workflow models
python codex-flow.py workflow models --json
```

| Model | Catalog role / effort | Flow dispatch | Evidence |
| --- | --- | --- | --- |
| `gpt-6.1-sol` | Chief / `xhigh` | Existing default | Historical native Flow execution verified |
| `gpt-6-luna` | Optional executor / `medium` | Existing optional wiring | Historical preflight reached HTTP 429 before a child ran |
| `gpt-6.1-terra` | Visual review, scoped code fix / `medium` | Disabled | Documented candidate; no account test or local quality comparison |

`default_effort` describes this catalog's role settings. Sol remains the strict
chief default; listing Terra adds no model substitution or dispatch allowance.
Native experiments remain paused. A dispatch flag describes wiring, not authority
to run a workflow. Validation status records historical Flow evidence, not current
account access. All three models report `native_account_verified: null`: the catalog
never checks the caller's account. Luna's historical 429 does not establish that
the model is unsupported.

OpenAI documents Terra for image and screen reasoning, computer use, and writing,
with `medium` as its default effort. Its model-selection guidance also identifies
scoped code fixes as a candidate use. These are reasons to retain a candidate,
not evidence that Terra beats Sol on this project's coding tasks.
See the [Terra model page](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
and [model-selection guidance](https://developers.openai.com/api/docs/guides/model-selection).

Terra requires CLI **0.159.0+** according to the
[official model guide](https://learn.chatgpt.com/docs/models).
`catalog(cli_version=...)` checks a supplied complete version, optionally prefixed
with `codex-cli `. It does not discover or execute the CLI. Omitted versions yield
`cli_compatible: null`; malformed or older versions yield `false`. A prerelease
of 0.159.0 is below that minimum. Passing the version check proves no account
entitlement, quota, tool availability, or successful execution.

The [October 26 release note](https://learn.chatgpt.com/docs/whats-new/october-26-30-2026)
announces Terra in Work and Codex on Plus, Pro, Business, Enterprise, and Edu.
Actual access can vary with product/version and workspace administrator controls.
`native_account_verified: null` for every model preserves that uncertainty.
The catalog makes no pricing or subscription-savings claim and never calls a paid API.
