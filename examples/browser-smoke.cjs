#!/usr/bin/env node
/** Read-only Playwright DOM smoke/latency probe. No dependencies installed. */
'use strict';
const path = require('node:path');
const { createRequire } = require('node:module');
const { performance } = require('node:perf_hooks');

function parse(argv) {
  const o = { engine: 'chromium', runs: 3, timeout: 20000 };
  for (const arg of argv) {
    const m = arg.match(/^--([a-z-]+)=(.*)$/);
    if (!m || !['engine', 'url', 'endpoint', 'runs', 'timeout'].includes(m[1])) {
      throw new Error(`Unknown option: ${arg}`);
    }
    o[m[1]] = m[2];
  }
  if (!o.url) throw new Error('Specify --url=https://example.com');
  if (!['chromium', 'cdp'].includes(o.engine)) throw new Error('Use --engine=chromium or --engine=cdp');
  const url = new URL(o.url);
  if (!['https:', 'http:'].includes(url.protocol)) throw new Error('URL scheme must be http/https');
  o.runs = Number(o.runs);
  o.timeout = Number(o.timeout);
  if (!Number.isInteger(o.runs) || o.runs < 1 || o.runs > 10) throw new Error('runs: integer 1-10');
  if (!Number.isInteger(o.timeout) || o.timeout < 1000 || o.timeout > 120000) throw new Error('timeout: integer 1000-120000');
  if (o.engine === 'cdp') {
    if (!o.endpoint) throw new Error('For CDP provide --endpoint=http://127.0.0.1:9222');
    const ep = new URL(o.endpoint);
    if (!['http:', 'ws:', 'https:', 'wss:'].includes(ep.protocol) ||
        !['127.0.0.1', 'localhost', '[::1]'].includes(ep.hostname)) {
      throw new Error('CDP endpoint must be a loopback HTTP/WS URL');
    }
  }
  return o;
}

function loadPlaywright() {
  const fromProject = createRequire(path.join(process.cwd(), 'package.json'));
  for (const lib of ['playwright', 'playwright-core']) {
    try { return fromProject(lib); } catch (err) {
      if (err.code !== 'MODULE_NOT_FOUND') throw err;
    }
  }
  throw new Error('No local playwright/playwright-core package; run inside a project that already uses it. No package was installed.');
}

async function main() {
  const opts = parse(process.argv.slice(2));
  const { chromium } = loadPlaywright();
  const start = performance.now();
  const browser = opts.engine === 'chromium'
    ? await chromium.launch({ headless: true, timeout: opts.timeout })
    : await chromium.connectOverCDP(opts.endpoint, { timeout: opts.timeout });
  const connectMs = Math.round(performance.now() - start);
  const timings = [];
  const statuses = [];
  try {
    for (let i = 0; i < opts.runs; i++) {
      const context = await browser.newContext();
      try {
        const page = await context.newPage();
        const t0 = performance.now();
        const response = await page.goto(opts.url, { waitUntil: 'domcontentloaded', timeout: opts.timeout });
        const present = await page.locator('body').count();
        const text = await page.locator('body').textContent({ timeout: opts.timeout });
        if (!present || !text.trim()) throw new Error('Empty body: smoke failed; not a valid benchmark.');
        // Does not print or save page contents, cookies, headers, or credentials.
        timings.push(Math.round(performance.now() - t0));
        statuses.push(response ? response.status() : null);
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
  const sorted = [...timings].sort((a,b) => a-b);
  const medianMs = sorted[Math.floor(sorted.length / 2)];
  console.log(JSON.stringify({ engine: opts.engine, runs: opts.runs, connectMs, medianMs, sampleMs: timings,
    httpStatuses: statuses, warning: 'DOM smoke only, not E2E/visual proof. Compare actual behavior with Chromium.' }, null, 2));
}

main().catch(err => { console.error(`Browser smoke failed: ${err.message}`); process.exitCode = 1; });
