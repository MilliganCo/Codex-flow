# Browser routing: use only when justified

This is the browser *necessity gate*, not a reason to launch a browser. Use with
Playwright, Puppeteer, browser MCP/CLI, browser-dependent debugging, crawling,
explicit visual QA, or required UI smoke/E2E. It is an optional companion to
`run.md` or `debug.md`. It does **not** change browser binaries, packages,
MCP backends, or Playwright config. User and higher-priority project rules win.

## Gate 1 — Is browser execution necessary at all?

**Default: NO.** A changed React/Vue/HTML/CSS file, installed Playwright package,
existing E2E folder, available browser MCP, or the phrase "check the UI" inside
an agent's own plan does not automatically justify opening a browser. Do not run
Playwright, screenshots, multi-viewport checks, browser automation, or a benchmark
merely to increase the appearance of verification.

Use a browser when *one* of these conditions holds:

1. The user explicitly requests browser/E2E, screenshot, responsive/visual QA,
   hands-on UI verification, reproduction of a browser interaction, or browser automation.
2. Applicable project, CI or release requirements explicitly mandate an E2E/browser
   suite for this change. Execute those required tests without weakening/skipping them.
3. The defect only occurs in a browser, or requires real navigation, focus, cookies,
   browser permissions, downloads, rendering or JS runtime behavior to reproduce.
4. A changed **critical user journey** (such as checkout/auth/file upload) cannot be
   adequately verified by narrower tests and browser-level behavior is material to
   acceptance. Document the concrete risk before opening a browser.

Otherwise use static inspection, lint/typecheck, unit/component/API/integration tests
and focused non-browser checks. For an optional browser check, report `NOT_RUN — not
required for this change`; never imply actual browser validation. If E2E is mandatory
but unavailable, report `BLOCKED/NOT_RUN` with the reason, not PASSED.

Do not automatically install or start a local web server solely to run optional E2E.
If a browser run is necessary, select a single changed happy/error path first; do
not browse every screen, repeat screenshots, or collect video/traces by default.
An existing CI-mandated suite retains its required scope and configuration.

## Gate 2 — Choose an engine only after Gate 1 passes

1. **Avoid unnecessary browser usage.** For authorized read-only DOM extraction where
   an HTTP endpoint supplies equivalent data, use the existing HTTP client unless
   actual browser behavior is the subject of the task.
2. **Fidelity before speed.** If a necessary check demands visual/UX/layout fidelity,
   pixel screenshots, browser compatibility, standard `playwright test`, permissions,
   service workers, media, mobile emulation, complex SPA navigation, WebAuthn,
   tracing/video or download semantics, use the specified real Chromium/Firefox/WebKit
   browser. Claim verified browser behavior only after actually running its required check.
3. **Fast DOM path: Obscura.** After Gate 1 passes, use the installed Obscura for
   compatible low-risk DOM extraction, JavaScript evaluation, link indexing and
   simple form interactions. Use the local helper/CDP connection below. Keep Chromium
   for mandatory E2E, visual checks and incompatible behavior. Obscura screenshots
   are not Chrome ground truth. **Lightpanda is disabled in this installation:** do
   not select, launch or fall back to it unless the user explicitly re-enables it.
4. **Keep the host engine explicit.** When a built-in Playwright skill/browser plugin
   controls its own browser and provides no CDP-endpoint option, DO NOT claim that
   `.connectOverCDP()` has changed it. Use the separate authorized local helper for
   eligible Obscura DOM tasks; keep required project/browser tooling unchanged.
5. **Never change a project's test runner invisibly.** `chromium.connectOverCDP()`
   drives *an existing* CDP server; it does not make `npx playwright test` run against
   Lightpanda/Obscura automatically. Standard fixtures or artifact support may fail.
   Do not edit Playwright config, override fixtures, snapshot baselines, CI or imports
   solely to force a faster engine without a scoped user request and verification.
6. **No silent install/proxy/cloud.** Do not download browsers, Docker images, build
   dependencies, proxy services, paid cloud sessions or browser skills to speed up a
   routine request. Ask permission for an experiment requiring installation. Bind CDP
   to `127.0.0.1` when possible; CDP can control pages and expose session data.

## Compatibility + fallback gate

For the Obscura fast path:

- Determine which engine/binary, version and current CDP endpoint actually exist.
  Do not infer installation merely from a cached skill name or repo dependency.
- Reuse existing compatibility evidence for the same browser version and API path.
  Obscura 0.2.4 passed the local DOM/filter/add/fetch checks on 2026-10-13; this does
  not establish compatibility with arbitrary sites or visual/E2E behavior. When a
  new path needs a probe, use one bounded check with expected DOM/data values, not
  just `page.title()`. Do not launch a second browser after every successful DOM task.
- If the smoke fails, a required API is unsupported, the page crashes, navigation
  hangs, or data differs, record that specific limitation and **fallback directly**
  to Chromium **at most once for the current task**. Stop Obscura before the fallback.
  Do not replay a potentially completed mutation blindly; first establish its result.
  If Chromium also fails, report the actual failure/blocker. Do not retry the same
  failing alternative, switch to Lightpanda or silently weaken tests.
- If it passes, prefer the faster engine only for matching eligible tasks. Use
  Chromium for the actual required fidelity gate, not automatically after every
  simple DOM pass. Browser versions can change behavior.
- Keep browser sessions short and scoped. Don't expose CDP on all network interfaces,
  share authenticated profiles, or persist traces/cookies without authorization.

## Connection patterns (only after server exists)

### Installed Windows helper

Executable: `<BrowserLab>\obscura\0.2.4\obscura.exe`.
The helper and its local config already exist outside working repositories:

```powershell
$lab = Join-Path $env:USERPROFILE 'Tools\CodexBrowserLab\browser-lab.cjs'
node $lab start obscura
# Only when the authorized target is a local/private-network server:
# node $lab start obscura --local-test
```

Connect to `ws://127.0.0.1:9222` using the existing project Playwright dependency,
or the already installed dependency named in the helper's `lab.config.json`.
No installation, benchmark, new server or instruction/config rewrite is required
for ordinary authorized DOM work. The helper refuses occupied ports; never stop
another process to acquire the endpoint.

For the single justified DOM fallback: `node $lab stop obscura`, then
`node $lab start chromium` and connect to `http://127.0.0.1:9224`. Required E2E
and visual checks still use the project's existing real-browser test runner,
fixtures and configuration, not this DOM helper as a substitute.
After the task, close the context/connection and run `node $lab stop obscura`
or `node $lab stop chromium` for the process you started. Start/stop alone does
not prove that page operations succeeded. Lightpanda start/test is blocked by
the helper; its binary and historical benchmark results remain untouched.

Obscura supports Playwright's `chromium.connectOverCDP()` path; it is **lower
fidelity than Playwright's own protocol**. `chromium.connect()` is a different protocol.

```js
const { chromium } = require('playwright');
const browser = await chromium.connectOverCDP('ws://127.0.0.1:9222');
try {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:3000', { waitUntil: 'domcontentloaded' });
  // Exercise one real workflow here; assert meaningful content/behavior.
  await ctx.close();
} finally {
  await browser.close();
}
```

You can compare this scenario on Chromium with `await chromium.launch()`
in a **separate** probe, but only if needed for a required fidelity check or an
explicitly requested benchmark. Do not create an obligatory second browser run.
Use an already installed project's Playwright package, not an unapproved install.
For empirical measurements, run `examples/browser-smoke.cjs` from the unpacked
archive using the project's local Playwright dependency. It is manual and opt-in:
never run it as part of every implementation or ordinary UI review.

## Windows notes

- **Obscura**: provides native Windows ZIP releases; use an official release from
  `h4ckf0r0day/obscura`. Choose a rendering-enabled build if screenshot is needed;
  still check result against Chrome. Do not blindly execute unverified binaries.
- **Lightpanda**: installed but disabled by the user's current routing choice. The
  tested 1.0.0/Playwright 1.61.1 pairing did not clear inputs with `locator.fill('')`.
- Native Obscura and WSL2 Lightpanda are alternatives, not dependencies of Codex Flow.
- If `localhost:9222` is already used, coordinate ports; never kill someone else's
  server. Only connect when you know which engine owns the endpoint.

## Expected reporting

If browser testing was necessary, state the engine actually used, why, the test
coverage and any fallback. If not necessary, state that browser UI verification
was intentionally skipped; do not overexplain on every tiny change.
Distinguish browser/execution timing from agent planning/model latency. No generic
"11x faster" claim without an apples-to-apples run on the user's own tasks.

### Primary references (checked 2026-10-13)

- Lightpanda docs: https://lightpanda.io/docs/quickstarts/skill
- Lightpanda CDP guide: https://lightpanda.io/docs/quickstarts/puppeteer-playwright-clients
- Obscura source: https://github.com/h4ckf0r0day/obscura
- Obscura + Playwright limits: https://github.com/h4ckf0r0day/obscura/blob/main/docs/Use-with-Playwright.md
- Playwright CDP caveat: https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp
