/**
 * Responsive viewport matrix smoke (#27).
 * Checks key public + auth pages at 320–1920 widths for horizontal overflow
 * and critical control visibility.
 *
 * Usage:
 *   BASE_URL=http://127.0.0.1:8000 SMOKE_TOKEN=<session> node tests/viewport-smoke.js
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const TOKEN = process.env.SMOKE_TOKEN || '';

const VIEWPORTS = [
  { width: 320, height: 568, name: '320' },
  { width: 375, height: 667, name: '375' },
  { width: 768, height: 1024, name: '768' },
  { width: 1024, height: 768, name: '1024' },
  { width: 1366, height: 768, name: '1366' },
  { width: 1920, height: 1080, name: '1920' },
];

const PUBLIC = ['/', '/about', '/faq', '/guides', '/privacy', '/udemycoupons'];
const AUTH = ['/dashboard', '/settings', '/history'];

async function measurePage(page, route) {
  const resp = await page.goto(`${BASE_URL}${route}`, {
    waitUntil: 'domcontentloaded',
    timeout: 30000,
  });
  await page.waitForTimeout(600);

  // Dismiss cookie banner if visible (can affect layout height, not width)
  try {
    const decline = page.locator('#cookie-decline');
    if (await decline.isVisible({ timeout: 300 }).catch(() => false)) {
      await decline.click();
      await page.waitForTimeout(200);
    }
  } catch (_) {}

  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    const scrollW = Math.max(doc.scrollWidth, body ? body.scrollWidth : 0);
    const clientW = doc.clientWidth;
    const overflowX = scrollW > clientW + 1;

    // Find widest overflowing elements (top offenders)
    const offenders = [];
    const all = document.querySelectorAll('body *');
    for (const el of all) {
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      // past viewport right edge significantly
      if (r.right > clientW + 2) {
        offenders.push({
          tag: el.tagName,
          id: el.id || '',
          cls: (el.className || '').toString().slice(0, 80),
          right: Math.round(r.right),
          width: Math.round(r.width),
        });
      }
    }
    offenders.sort((a, b) => b.right - a.right);

    const h1 = document.querySelectorAll('h1').length;
    const main = document.querySelector('main, #main-content, [role="main"]');
    const mainVisible = !!(main && main.getBoundingClientRect().height > 20);

    return {
      scrollW,
      clientW,
      overflowX,
      overflowPx: Math.max(0, scrollW - clientW),
      offenders: offenders.slice(0, 6),
      h1,
      mainVisible,
      title: document.title || '',
    };
  });

  const issues = [];
  const status = resp ? resp.status() : 0;
  if (status !== 200) issues.push(`status ${status}`);
  if (metrics.overflowX) {
    issues.push(`horizontal overflow ${metrics.overflowPx}px (scrollW=${metrics.scrollW})`);
  }
  if (metrics.h1 < 1) issues.push('missing h1');
  if (!metrics.mainVisible) issues.push('main not visible');

  // Route-specific critical controls
  if (route === '/dashboard') {
    const start = page.locator('#start-btn');
    if (!(await start.count()) || !(await start.isVisible())) {
      issues.push('start-btn not visible');
    }
  }
  if (route === '/settings') {
    const save = page.locator('button:has-text("Save Settings")');
    if (!(await save.count()) || !(await save.isVisible())) {
      issues.push('Save Settings not visible');
    }
  }
  if (route === '/udemycoupons') {
    const search = page.locator('#searchInput');
    if (!(await search.count()) || !(await search.isVisible())) {
      issues.push('searchInput not visible');
    }
  }
  if (route === '/') {
    const connect = page.locator('#connect, [id="connect"], a[href="#connect"], #connect-heading');
    // soft: at least hero h1 exists (already checked)
  }

  return {
    route,
    status,
    ...metrics,
    issues,
    ok: issues.length === 0,
  };
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const report = {
    generated_at: new Date().toISOString(),
    base_url: BASE_URL,
    viewports: [],
  };

  console.log(`Base: ${BASE_URL}`);
  console.log(`Token: ${TOKEN ? 'set' : 'missing (auth routes skipped)'}`);

  for (const vp of VIEWPORTS) {
    console.log(`\n=== ${vp.name} (${vp.width}x${vp.height}) ===`);
    const entry = { viewport: vp, public: [], auth: [] };
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
    });
    await context.route('**/api/**/stream**', (r) => r.abort());
    const page = await context.newPage();

    for (const route of PUBLIC) {
      try {
        const r = await measurePage(page, route);
        entry.public.push(r);
        if (!r.ok) console.log('  FAIL', route, r.issues.join('; '));
        else console.log('  ok  ', route, r.overflowX ? `overflow ${r.overflowPx}` : '');
      } catch (e) {
        entry.public.push({ route, ok: false, issues: [e.message] });
        console.log('  FAIL', route, e.message);
      }
    }

    if (TOKEN) {
      await context.addCookies([
        { name: 'session_id', value: TOKEN, url: BASE_URL },
      ]);
      for (const route of AUTH) {
        try {
          const r = await measurePage(page, route);
          // auth may redirect if token invalid
          if (!page.url().includes(route.replace('/', '')) && !page.url().includes(route)) {
            r.issues.push(`redirected ${page.url()}`);
            r.ok = false;
          }
          entry.auth.push(r);
          if (!r.ok) console.log('  FAIL', route, r.issues.join('; '));
          else console.log('  ok  ', route);
        } catch (e) {
          entry.auth.push({ route, ok: false, issues: [e.message] });
          console.log('  FAIL', route, e.message);
        }
      }
    }

    report.viewports.push(entry);
    await context.close();
  }

  await browser.close();

  const failures = [];
  for (const v of report.viewports) {
    for (const r of [...v.public, ...v.auth]) {
      if (!r.ok) {
        failures.push({
          viewport: v.viewport.name,
          route: r.route,
          issues: r.issues,
          offenders: r.offenders || [],
        });
      }
    }
  }

  report.summary = {
    viewports: VIEWPORTS.length,
    failure_count: failures.length,
    failures,
  };

  const outDir = path.join(__dirname, '..', 'performance-report');
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, 'viewport-smoke-latest.json'),
    JSON.stringify(report, null, 2),
  );
  fs.writeFileSync(
    path.join(__dirname, 'viewport-smoke-summary.json'),
    JSON.stringify(
      {
        generated_at: report.generated_at,
        base_url: report.base_url,
        failure_count: failures.length,
        failures,
        pass:
          report.viewports.flatMap((v) => [...v.public, ...v.auth]).filter((r) => r.ok)
            .length,
        total: report.viewports.flatMap((v) => [...v.public, ...v.auth]).length,
      },
      null,
      2,
    ),
  );

  console.log(`\nFailures: ${failures.length}`);
  for (const f of failures) {
    console.log(`- ${f.viewport} ${f.route}: ${f.issues.join('; ')}`);
    if (f.offenders && f.offenders[0]) {
      console.log(
        `  top offender: <${f.offenders[0].tag}>#${f.offenders[0].id} .${f.offenders[0].cls} right=${f.offenders[0].right}`,
      );
    }
  }

  process.exit(failures.length ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
