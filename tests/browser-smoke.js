/**
 * Multi-browser smoke (optional #26).
 * Public routes + authenticated shell (dashboard/settings/history).
 *
 * Usage:
 *   SMOKE_TOKEN=<session_id> node tests/browser-smoke.js
 *   BASE_URL=http://127.0.0.1:8000 SMOKE_TOKEN=... node tests/browser-smoke.js
 *   BROWSERS=chromium,firefox,webkit node tests/browser-smoke.js
 *
 * Does not call real Udemy. Token should be a local session with fake cookies.
 */

const { chromium, firefox, webkit } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.BASE_URL || process.env.PERF_BASE_URL || 'http://127.0.0.1:8000';
const TOKEN = process.env.SMOKE_TOKEN || '';
const BROWSERS = (process.env.BROWSERS || 'chromium,firefox,webkit')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

const PUBLIC_ROUTES = [
  '/',
  '/about',
  '/faq',
  '/guides',
  '/privacy',
  '/udemycoupons',
];

const AUTH_ROUTES = ['/dashboard', '/settings', '/history'];

const REPORT_DIR = path.join(__dirname, '..', 'performance-report');
const ENGINES = { chromium, firefox, webkit };

async function checkPublic(page, route) {
  const resp = await page.goto(`${BASE_URL}${route}`, {
    waitUntil: 'domcontentloaded',
    timeout: 30000,
  });
  const status = resp ? resp.status() : 0;
  await page.waitForTimeout(400);
  const issues = [];
  if (status !== 200) issues.push(`status ${status}`);
  if (!page.url().includes(route.replace(/\/$/, '') || route) && route !== '/') {
    // allow trailing-slash redirects ending on same path
    if (!page.url().includes(route)) issues.push(`unexpected url ${page.url()}`);
  }
  const h1 = await page.locator('h1').count();
  if (h1 < 1) issues.push('missing h1');
  const main = await page.locator('main, #main-content, [role="main"]').count();
  if (main < 1) issues.push('missing main landmark');
  const lang = await page.evaluate(() => document.documentElement.lang);
  if (!lang) issues.push('missing html lang');
  // no hard JS error banner
  const title = await page.title();
  if (!title || title.length < 3) issues.push('empty title');
  return { route, status, title, h1, issues, ok: issues.length === 0 };
}

async function checkAuth(page, route) {
  const resp = await page.goto(`${BASE_URL}${route}`, {
    waitUntil: 'domcontentloaded',
    timeout: 30000,
  });
  await page.waitForTimeout(1200);
  const issues = [];
  const status = resp ? resp.status() : 0;
  if (status !== 200) issues.push(`status ${status}`);
  // client may redirect if unauthenticated
  if (!page.url().includes(route)) {
    issues.push(`redirected to ${page.url()} (auth shell not available)`);
  } else {
    const h1 = await page.locator('h1').count();
    if (h1 < 1) issues.push('missing h1');
    if (route === '/dashboard') {
      const start = await page.locator('#start-btn').count();
      if (!start) issues.push('missing #start-btn');
    }
    if (route === '/settings') {
      const save = await page.locator('button:has-text("Save Settings")').count();
      if (!save) issues.push('missing Save Settings');
    }
    if (route === '/history') {
      const sync = await page.locator('button:has-text("Sync Data")').count();
      if (!sync) issues.push('missing Sync Data');
    }
  }
  return { route, status, url: page.url(), issues, ok: issues.length === 0 };
}

async function runBrowser(name) {
  const launcher = ENGINES[name];
  if (!launcher) throw new Error(`Unknown browser ${name}`);
  const result = {
    browser: name,
    public: [],
    auth: [],
    errors: [],
  };
  let browser;
  try {
    browser = await launcher.launch({ headless: true });
  } catch (e) {
    const msg = e.message || String(e);
    result.errors.push(`launch failed: ${msg}`);
    // Host OS missing shared libraries (common for WebKit without install-deps)
    if (/missing dependencies|install-deps|libavif/i.test(msg)) {
      result.skipped = true;
      result.skip_reason = 'host_missing_browser_dependencies';
    }
    return result;
  }

  try {
    // Public
    const pubCtx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const pubPage = await pubCtx.newPage();
    pubPage.on('pageerror', (err) => {
      result.errors.push(`pageerror public: ${err.message}`);
    });
    for (const route of PUBLIC_ROUTES) {
      try {
        result.public.push(await checkPublic(pubPage, route));
      } catch (e) {
        result.public.push({ route, ok: false, issues: [e.message] });
      }
    }
    await pubCtx.close();

    // Auth shell
    if (TOKEN) {
      const authCtx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
      await authCtx.addCookies([
        { name: 'session_id', value: TOKEN, url: BASE_URL },
      ]);
      const authPage = await authCtx.newPage();
      authPage.on('pageerror', (err) => {
        result.errors.push(`pageerror auth: ${err.message}`);
      });
      // Block long-lived SSE
      await authPage.route('**/api/**/stream**', (r) => r.abort());
      for (const route of AUTH_ROUTES) {
        try {
          result.auth.push(await checkAuth(authPage, route));
        } catch (e) {
          result.auth.push({ route, ok: false, issues: [e.message] });
        }
      }
      // keyboard smoke: start confirm Escape
      try {
        await authPage.goto(`${BASE_URL}/dashboard`, {
          waitUntil: 'domcontentloaded',
          timeout: 30000,
        });
        await authPage.waitForTimeout(800);
        if (await authPage.locator('#start-btn').isVisible()) {
          await authPage.locator('#start-btn').focus();
          await authPage.keyboard.press('Enter');
          await authPage.waitForTimeout(300);
          const open = await authPage.evaluate(
            () =>
              !document
                .getElementById('a11y-confirm-root')
                ?.classList.contains('hidden'),
          );
          await authPage.keyboard.press('Escape');
          await authPage.waitForTimeout(200);
          const closed = await authPage.evaluate(
            () =>
              document
                .getElementById('a11y-confirm-root')
                ?.classList.contains('hidden') !== false,
          );
          result.auth.push({
            route: '/dashboard#confirm',
            ok: open && closed,
            issues: [
              ...(open ? [] : ['confirm did not open']),
              ...(closed ? [] : ['confirm did not close on Escape']),
            ],
          });
        }
      } catch (e) {
        result.auth.push({
          route: '/dashboard#confirm',
          ok: false,
          issues: [e.message],
        });
      }
      await authCtx.close();
    } else {
      result.errors.push('SMOKE_TOKEN not set; skipped auth routes');
    }
  } finally {
    await browser.close();
  }

  if (result.skipped) {
    result.ok = true; // environment skip, not an app failure
    return result;
  }
  result.ok =
    result.errors.filter((e) => !e.includes('SMOKE_TOKEN')).length === 0 &&
    result.public.every((r) => r.ok) &&
    (result.auth.length === 0 || result.auth.every((r) => r.ok));
  return result;
}

async function main() {
  console.log(`Base: ${BASE_URL}`);
  console.log(`Browsers: ${BROWSERS.join(', ')}`);
  console.log(`Auth token: ${TOKEN ? 'set' : 'missing'}`);

  const report = {
    generated_at: new Date().toISOString(),
    base_url: BASE_URL,
    browsers: [],
  };

  for (const name of BROWSERS) {
    console.log(`\n=== ${name} ===`);
    const r = await runBrowser(name);
    report.browsers.push(r);
    const pubPass = r.public.filter((x) => x.ok).length;
    const authPass = r.auth.filter((x) => x.ok).length;
    console.log(
      `public ${pubPass}/${r.public.length}  auth ${authPass}/${r.auth.length}  errors ${r.errors.length}`,
    );
    for (const row of [...r.public, ...r.auth]) {
      if (!row.ok) console.log('  FAIL', row.route, row.issues);
    }
    for (const e of r.errors) console.log('  ERR', e);
  }

  if (!fs.existsSync(REPORT_DIR)) fs.mkdirSync(REPORT_DIR, { recursive: true });
  const out = path.join(REPORT_DIR, 'browser-smoke-latest.json');
  fs.writeFileSync(out, JSON.stringify(report, null, 2));
  // Also keep a tracked-friendly copy under docs when possible via summary
  const summaryPath = path.join(__dirname, 'browser-smoke-summary.json');
  const summary = {
    generated_at: report.generated_at,
    base_url: report.base_url,
    results: report.browsers.map((b) => ({
      browser: b.browser,
      ok: b.ok,
      skipped: !!b.skipped,
      skip_reason: b.skip_reason || null,
      public_pass: b.public.filter((x) => x.ok).length,
      public_total: b.public.length,
      auth_pass: b.auth.filter((x) => x.ok).length,
      auth_total: b.auth.length,
      failures: [...b.public, ...b.auth]
        .filter((x) => !x.ok)
        .map((x) => ({ route: x.route, issues: x.issues })),
      errors: b.errors,
    })),
  };
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));
  console.log(`\nWrote ${out}`);
  console.log(`Wrote ${summaryPath}`);

  const ran = report.browsers.filter((b) => !b.skipped);
  const skipped = report.browsers.filter((b) => b.skipped);
  if (skipped.length) {
    console.log(
      `\nSkipped (host deps): ${skipped.map((b) => b.browser).join(', ')}`,
    );
  }
  const allOk = ran.length > 0 && ran.every((b) => b.ok);
  // Fail only if a launched browser failed app checks, or nothing ran
  process.exit(allOk ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
