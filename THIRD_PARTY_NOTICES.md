# Third-party references and distribution boundaries

This repository develops the pre-existing bespoke Codex Flow 1.2.0 skill. `SOURCES.md` records its original design provenance. The new runtime uses Python's standard library and invokes separately installed tools. **No project license has been selected.** This file records references; it does not grant rights or substitute for a source/dependency license inventory.

| Component/reference | Relationship to this repository |
|---|---|
| [OpenAI Codex CLI](https://github.com/openai/codex) | Separately installed executable and native subscription interface; no CLI binary/source bundled by the runtime |
| [Google Research Harness²](https://github.com/google-research/harness2) | Research reference for local measured proposal comparison; upstream executor is not bundled or launched |
| [OpenRouter Mercury Decide free route](https://openrouter.ai/inception/mercury-decide:free) | Optional external service reached through an explicitly selected external adapter |
| [Python](https://www.python.org/) | Required separately installed runtime; project modules use its standard library |
| [Obscura](https://github.com/h4ckf0r0day/obscura), [Lightpanda](https://github.com/lightpanda-io/browser), [Playwright](https://github.com/microsoft/playwright) | Existing conditional browser-route references/examples; browser tools are not required or installed by ordinary runtime execution |

The existing external Mercury decision client and credential helper are **unbundled and not redistributed**. Local availability or interoperability does not establish redistribution permission. No keys, native auth files or personal installation manifests belong in the repository.

The legacy skill's original provenance also references native Codex documentation and workflow ideas. Retain `SOURCES.md` and its distinction between original package text and referenced upstream material. References do not imply endorsement by those projects.

Before adding any third-party source, binary, copied documentation or dependency, record the exact version/source, review its license and include required notices in the same reviewed change. See [license options](docs/license-options.md) for the pending owner decision.
