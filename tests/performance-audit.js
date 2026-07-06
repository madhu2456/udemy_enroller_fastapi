/**
 * Core Web Vitals performance baseline audit.
 * Measures public routes with Playwright + Performance API.
 *
 * Usage:
 *   node tests/performance-audit.js
 *   PERF_BASE_URL=http://127.0.0.1:8000 node tests/performance-audit.js --write-baseline
 *   node tests/performance-audit.js --check
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.PERF_BASE_URL || 'https://udemyenroller.madhudadi.in';
const REPORT_DIR = path.join(__dirname, '..', 'performance-report');
const BASELINE_PATH = path.join(__dirname, 'performance-baseline.json');
const TIMEOUT = 45000;
const SETTLE_MS = 3000;

const PUBLIC_ROUTES = [
  { path: '/', name: 'Home' },
  { path: '/udemycoupons', name: 'Free Coupons' },
  { path: '/faq', name: 'FAQ' },
  { path: '/about', name: 'About' },
  { path: '/guides', name: 'Guides' },
  { path: '/privacy', name: 'Privacy' },
];

const VIEWPORTS = [
  { width: 375, height: 667, name: 'mobile' },
  { width: 1366, height: 768, name: 'desktop' },
];

const CWV_THRESHOLDS = {
  lcp_ms: { good: 2500, poor: 4000 },
  fcp_ms: { good: 1800, poor: 3000 },
  cls: { good: 0.1, poor: 0.25 },
  ttfb_ms: { good: 800, poor: 1800 },
};

// Live-site audits vary with network/CDN latency; flag only large regressions.
const CHECK_TOLERANCE = {
  timing_ratio: 2.5,
  timing_abs_ms: 1500,
  cls_poor: 0.25,
};

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function rateMetric(metric, value) {
  if (value == null || Number.isNaN(value)) {
    return 'unknown';
  }
  const thresholds = CWV_THRESHOLDS[metric];
  if (!thresholds) {
    return 'n/a';
  }
  if (value <= thresholds.good) {
    return 'good';
  }
  if (value <= thresholds.poor) {
    return 'needs-improvement';
  }
  return 'poor';
}

async function collectMetrics(page) {
  await page.waitForTimeout(SETTLE_MS);

  return page.evaluate(() => {
    return new Promise((resolve) => {
      const metrics = {
        ttfb_ms: null,
        fcp_ms: null,
        lcp_ms: null,
        cls: 0,
        dom_content_loaded_ms: null,
        load_ms: null,
        request_count: 0,
        transfer_bytes: 0,
      };

      const navigation = performance.getEntriesByType('navigation')[0];
      if (navigation) {
        metrics.ttfb_ms = Math.round(navigation.responseStart);
        metrics.dom_content_loaded_ms = Math.round(
          navigation.domContentLoadedEventEnd
        );
        metrics.load_ms = Math.round(navigation.loadEventEnd);
      }

      const paints = performance.getEntriesByType('paint');
      const fcp = paints.find((entry) => entry.name === 'first-contentful-paint');
      if (fcp) {
        metrics.fcp_ms = Math.round(fcp.startTime);
      }

      let lcpValue = 0;
      const lcpObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1];
        if (last) {
          lcpValue = last.startTime;
        }
      });
      lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });

      let clsValue = 0;
      const clsObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) {
            clsValue += entry.value;
          }
        }
      });
      clsObserver.observe({ type: 'layout-shift', buffered: true });

      const resources = performance.getEntriesByType('resource');
      metrics.request_count = resources.length;
      metrics.transfer_bytes = resources.reduce(
        (sum, entry) => sum + (entry.transferSize || 0),
        0
      );

      setTimeout(() => {
        metrics.lcp_ms = lcpValue ? Math.round(lcpValue) : null;
        metrics.cls = Number(clsValue.toFixed(4));
        resolve(metrics);
      }, 1500);
    });
  });
}

async function auditRoute(browser, route, viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    userAgent:
      viewport.name === 'mobile'
        ? 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        : undefined,
  });
  const page = await context.newPage();
  const url = `${BASE_URL}${route.path}`;

  try {
    const response = await page.goto(url, {
      waitUntil: 'networkidle',
      timeout: TIMEOUT,
    });
    const metrics = await collectMetrics(page);

    return {
      path: route.path,
      name: route.name,
      url,
      viewport: viewport.name,
      status: response ? response.status() : null,
      metrics,
      ratings: {
        ttfb: rateMetric('ttfb_ms', metrics.ttfb_ms),
        fcp: rateMetric('fcp_ms', metrics.fcp_ms),
        lcp: rateMetric('lcp_ms', metrics.lcp_ms),
        cls: rateMetric('cls', metrics.cls),
      },
      timestamp: new Date().toISOString(),
    };
  } finally {
    await context.close();
  }
}

function groupResults(results) {
  const routes = [];

  for (const route of PUBLIC_ROUTES) {
    const routeResults = results.filter((item) => item.path === route.path);
    routes.push({
      path: route.path,
      name: route.name,
      viewports: routeResults.map((item) => ({
        name: item.viewport,
        width: VIEWPORTS.find((vp) => vp.name === item.viewport)?.width,
        status: item.status,
        metrics: item.metrics,
        ratings: item.ratings,
        timestamp: item.timestamp,
      })),
    });
  }

  return routes;
}

function summarize(results) {
  const rated = results.filter((item) => item.ratings.lcp !== 'unknown');
  const goodLcp = rated.filter((item) => item.ratings.lcp === 'good').length;
  const poorLcp = rated.filter((item) => item.ratings.lcp === 'poor').length;
  const poorCls = rated.filter((item) => item.ratings.cls === 'poor').length;
  const slowTtfb = rated.filter(
    (item) => item.ratings.ttfb === 'needs-improvement'
  ).length;

  const findings = [];
  if (poorCls > 0) {
    findings.push(
      `${poorCls} viewport(s) have poor CLS (>= ${CWV_THRESHOLDS.cls.poor}); likely dynamic content or late-loading assets.`
    );
  }
  if (slowTtfb > 0) {
    findings.push(
      `${slowTtfb} viewport(s) have TTFB in needs-improvement range (>${CWV_THRESHOLDS.ttfb_ms.good}ms).`
    );
  }
  if (poorLcp > 0) {
    findings.push(`${poorLcp} viewport(s) have poor LCP (>${CWV_THRESHOLDS.lcp_ms.poor}ms).`);
  }

  return {
    routes_tested: PUBLIC_ROUTES.length,
    measurements: results.length,
    lcp_good: goodLcp,
    lcp_poor: poorLcp,
    cls_poor: poorCls,
    ttfb_needs_improvement: slowTtfb,
    thresholds: CWV_THRESHOLDS,
    findings,
  };
}

function buildReport(results) {
  return {
    generated_at: new Date().toISOString(),
    base_url: BASE_URL,
    tool: 'performance-audit.js',
    tool_version: '1.0.0',
    summary: summarize(results),
    routes: groupResults(results),
  };
}

function findBaselineMeasurement(baseline, path, viewport) {
  const route = baseline.routes.find((item) => item.path === path);
  if (!route) {
    return null;
  }
  return route.viewports.find((item) => item.name === viewport) || null;
}

function compareAgainstBaseline(report, baseline) {
  const regressions = [];

  for (const result of report.routes) {
    for (const viewport of result.viewports) {
      const baselineViewport = findBaselineMeasurement(
        baseline,
        result.path,
        viewport.name
      );
      if (!baselineViewport) {
        regressions.push({
          path: result.path,
          viewport: viewport.name,
          metric: 'route',
          message: 'Missing baseline entry',
        });
        continue;
      }

      const baselineMetrics = baselineViewport.metrics;
      const currentMetrics = viewport.metrics;

      for (const [metric, value] of Object.entries(currentMetrics)) {
        const baselineValue = baselineMetrics[metric];
        if (
          baselineValue == null ||
          value == null ||
          ['request_count', 'transfer_bytes'].includes(metric)
        ) {
          continue;
        }

        if (metric === 'cls') {
          if (
            baselineValue <= CWV_THRESHOLDS.cls.good &&
            value >= CHECK_TOLERANCE.cls_poor
          ) {
            regressions.push({
              path: result.path,
              viewport: viewport.name,
              metric,
              baseline: baselineValue,
              current: value,
              message: `CLS crossed poor threshold (${CHECK_TOLERANCE.cls_poor})`,
            });
          }
          continue;
        }

        const limit = Math.max(
          baselineValue * CHECK_TOLERANCE.timing_ratio,
          baselineValue + CHECK_TOLERANCE.timing_abs_ms
        );
        if (value > limit) {
          regressions.push({
            path: result.path,
            viewport: viewport.name,
            metric,
            baseline: baselineValue,
            current: value,
            message: `${metric} exceeded baseline tolerance (${Math.round(limit)}ms)`,
          });
        }
      }
    }
  }

  return regressions;
}

async function runAudit() {
  ensureDir(REPORT_DIR);

  const browser = await chromium.launch({ headless: true });
  const results = [];

  try {
    for (const route of PUBLIC_ROUTES) {
      for (const viewport of VIEWPORTS) {
        process.stdout.write(`Measuring ${route.path} @ ${viewport.name}... `);
        const result = await auditRoute(browser, route, viewport);
        results.push(result);
        console.log(
          `LCP ${result.metrics.lcp_ms ?? 'n/a'}ms, CLS ${result.metrics.cls}`
        );
      }
    }
  } finally {
    await browser.close();
  }

  const report = buildReport(results);
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const reportPath = path.join(REPORT_DIR, `performance-${stamp}.json`);
  const latestPath = path.join(REPORT_DIR, 'performance-latest.json');

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  fs.writeFileSync(latestPath, JSON.stringify(report, null, 2));

  console.log(`\nReport saved: ${reportPath}`);
  return report;
}

async function main() {
  const writeBaseline = process.argv.includes('--write-baseline');
  const checkBaseline = process.argv.includes('--check');

  const report = await runAudit();

  if (writeBaseline) {
    const baseline = {
      generated_at: report.generated_at,
      base_url: report.base_url,
      tool_version: report.tool_version,
      summary: report.summary,
      routes: report.routes,
    };
    fs.writeFileSync(BASELINE_PATH, JSON.stringify(baseline, null, 2));
    console.log(`Baseline updated: ${BASELINE_PATH}`);
  }

  if (checkBaseline) {
    if (!fs.existsSync(BASELINE_PATH)) {
      console.error(`Baseline file not found: ${BASELINE_PATH}`);
      process.exit(1);
    }

    const baseline = JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf8'));
    const regressions = compareAgainstBaseline(report, baseline);

    if (regressions.length > 0) {
      console.error('\nPerformance regressions detected:');
      for (const regression of regressions) {
        console.error(
          `- ${regression.path} (${regression.viewport}) ${regression.metric}: ${regression.message}`
        );
      }
      process.exit(1);
    }

    console.log('\nNo performance regressions against baseline.');
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});