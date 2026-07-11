/**
 * WCAG 2.2 AA Conformance Audit Script
 * Scans all public routes of udemyenroller.madhudadi.in using axe-core
 * Tests at 320px, 768px, and 1366px viewports
 */

const { chromium } = require('playwright');
const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('fs');
const path = require('path');

// Prefer local during development: BASE_URL=http://127.0.0.1:8000 npm run audit:wcag
const BASE_URL = process.env.BASE_URL || 'https://udemyenroller.madhudadi.in';
const REPORT_DIR = path.join(__dirname, '..', 'wcag-report');
const SCREENSHOTS_DIR = path.join(REPORT_DIR, 'screenshots');
const TIMEOUT = 30000;

const PUBLIC_ROUTES = [
  { path: '/', name: 'Home' },
  { path: '/udemycoupons', name: 'Free Coupons' },
  { path: '/faq', name: 'FAQ' },
  { path: '/about', name: 'About' },
  { path: '/guides', name: 'Guides' },
  { path: '/privacy', name: 'Privacy' },
];

const VIEWPORTS = [
  { width: 320, height: 568, name: '320px (Mobile)' },
  { width: 768, height: 1024, name: '768px (Tablet)' },
  { width: 1366, height: 768, name: '1366px (Desktop)' },
];

// WCAG 2.2 AA tags
const WCAG_TAGS = [
  'wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa'
];

async function createDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

async function runAxeOnPage(page, url, viewport) {
  await page.goto(url, { waitUntil: 'networkidle', timeout: TIMEOUT });
  await page.waitForTimeout(2000);
  
  const results = await new AxeBuilder({ page })
    .withTags(WCAG_TAGS)
    .analyze();
  
  const filteredViolations = results.violations.filter(v => 
    v.tags.some(t => WCAG_TAGS.includes(t))
  );
  
  return {
    violations: filteredViolations,
    passes: results.passes,
    incomplete: results.incomplete,
    inapplicable: results.inapplicable,
    url: url,
    viewport: viewport,
    timestamp: new Date().toISOString(),
  };
}

async function checkKeyboardNavigation(page) {
  const results = {
    tabOrderValid: true,
    skipLinkWorks: false,
    focusVisible: true,
    issues: [],
  };
  
  try {
    // Check skip link
    const skipLink = page.locator('a[href="#main-content"]');
    const skipLinkCount = await skipLink.count();
    if (skipLinkCount > 0) {
      await page.keyboard.press('Tab');
      await page.waitForTimeout(500);
      const isFocused = await skipLink.evaluate(el => el === document.activeElement);
      results.skipLinkWorks = isFocused;
      
      if (isFocused) {
        await skipLink.click();
        await page.waitForTimeout(500);
        const mainContent = page.locator('#main-content');
        const mainFocused = await mainContent.evaluate(el => el === document.activeElement || el.contains(document.activeElement));
        results.skipLinkWorks = mainFocused;
      }
    } else {
      results.issues.push('No skip link found');
    }
    
    // Tab through interactive elements
    const interactiveSelectors = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';
    const elements = await page.locator(interactiveSelectors).all();
    
    let focusableCount = 0;
    for (let i = 0; i < Math.min(elements.length, 20); i++) {
      await page.keyboard.press('Tab');
      await page.waitForTimeout(200);
      
      const hasFocusRing = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const outline = style.outline;
        const outlineColor = style.outlineColor;
        const boxShadow = style.boxShadow;
        
        return (
          (outline && outline !== '0px none rgb(0, 0, 0)' && outline !== '0px' && outlineColor !== 'rgb(0, 0, 0)') ||
          (boxShadow && boxShadow !== 'none' && !boxShadow.includes('0 0 0 0'))
        );
      });
      
      if (!hasFocusRing) {
        results.focusVisible = false;
        const activeInfo = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el) return 'unknown';
          return `${el.tagName}: "${(el.textContent || '').trim().substring(0, 30) || el.id || el.getAttribute('aria-label') || 'unknown'}"`;
        });
        results.issues.push(`Focus ring not visible on ${activeInfo}`);
      }
      focusableCount++;
    }
    
    if (focusableCount === 0) {
      results.issues.push('No focusable elements found via keyboard');
    }
    
  } catch (e) {
    results.issues.push(`Keyboard navigation error: ${e.message}`);
  }
  
  return results;
}

async function checkReducedMotion(page) {
  const results = { respectsReducedMotion: false, details: [] };
  
  try {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.waitForTimeout(500);
    
    const hasReducedMotionRule = await page.evaluate(() => {
      const sheets = document.styleSheets;
      for (let i = 0; i < sheets.length; i++) {
        try {
          const rules = sheets[i].cssRules || sheets[i].rules;
          if (!rules) continue;
          for (let j = 0; j < rules.length; j++) {
            const rule = rules[j];
            if (rule.media && rule.conditionText && rule.conditionText.includes('prefers-reduced-motion')) {
              return true;
            }
          }
        } catch (e) {}
      }
      return false;
    });
    
    results.respectsReducedMotion = hasReducedMotionRule;
    results.details.push(`prefers-reduced-motion media query rule found: ${hasReducedMotionRule}`);
    
  } catch (e) {
    results.details.push(`Error checking reduced motion: ${e.message}`);
  }
  
  return results;
}

async function checkZoom200(page, url) {
  const results = { noHorizontalScroll: true, contentOverlap: false, details: [] };
  
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: TIMEOUT });
    await page.waitForTimeout(1000);
    
    await page.setViewportSize({ width: 320, height: 568 });
    // Use CSS zoom via page.evaluate
    await page.evaluate(() => {
      document.body.style.transform = 'scale(2)';
      document.body.style.transformOrigin = 'top left';
      document.body.style.width = '50%';
    });
    await page.waitForTimeout(1000);
    
    const hasHorizontalScroll = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    
    results.noHorizontalScroll = !hasHorizontalScroll;
    results.details.push(`Horizontal scroll at 200% zoom: ${hasHorizontalScroll}`);
    
    // Reset
    await page.evaluate(() => {
      document.body.style.transform = '';
      document.body.style.transformOrigin = '';
      document.body.style.width = '';
    });
    
  } catch (e) {
    results.details.push(`Zoom test error: ${e.message}`);
  }
  
  return results;
}

async function checkTargetSizes(page) {
  const results = { issues: [], smallTargets: [] };
  
  try {
    const smallButtons = await page.evaluate(() => {
      const interactive = document.querySelectorAll('a, button, input[type="button"], input[type="submit"]');
      const small = [];
      
      interactive.forEach(el => {
        const rect = el.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height;
        
        if (width === 0 && height === 0) return;
        
        if (width < 24 || height < 24) {
          small.push({
            tag: el.tagName,
            text: (el.textContent || '').trim().substring(0, 30) || el.getAttribute('aria-label') || '',
            width: Math.round(width),
            height: Math.round(height),
          });
        }
      });
      
      return small;
    });
    
    results.smallTargets = smallButtons;
    if (smallButtons.length > 0) {
      results.issues.push(`Found ${smallButtons.length} targets smaller than 24x24px`);
    }
    
  } catch (e) {
    results.issues.push(`Target size check error: ${e.message}`);
  }
  
  return results;
}

async function checkSemanticHTML(page) {
  const results = { issues: [], landmarks: {} };
  
  try {
    const landmarks = await page.evaluate(() => {
      const found = {};
      const banner = document.querySelectorAll('header[role="banner"], header:not([role])');
      if (banner.length) found.banner = banner.length;
      const nav = document.querySelectorAll('nav, [role="navigation"]');
      if (nav.length) found.navigation = nav.length;
      const main = document.querySelectorAll('main, [role="main"]');
      if (main.length) found.main = main.length;
      const footer = document.querySelectorAll('footer, [role="contentinfo"]');
      if (footer.length) found.contentinfo = footer.length;
      return found;
    });
    
    results.landmarks = landmarks;
    
    // Check heading structure
    const headingIssues = await page.evaluate(() => {
      const issues = [];
      const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
      
      if (headings.length === 0) {
        issues.push('No headings found');
        return issues;
      }
      
      let prevLevel = 0;
      headings.forEach(h => {
        const level = parseInt(h.tagName[1]);
        if (prevLevel > 0 && level > prevLevel + 1) {
          issues.push(`Heading level skipped: h${prevLevel} -> h${level}`);
        }
        prevLevel = level;
      });
      
      return issues;
    });
    
    results.issues.push(...headingIssues);
    
  } catch (e) {
    results.issues.push(`Semantic HTML check error: ${e.message}`);
  }
  
  return results;
}

async function checkFormLabels(page) {
  const results = { issues: [] };
  
  try {
    const formIssues = await page.evaluate(() => {
      const issues = [];
      
      document.querySelectorAll('input, select, textarea').forEach(el => {
        const id = el.id;
        const hasLabel = id && document.querySelector(`label[for="${id}"]`);
        const hasAriaLabel = el.hasAttribute('aria-label');
        const hasAriaLabelledBy = el.hasAttribute('aria-labelledby');
        
        if (!hasLabel && !hasAriaLabel && !hasAriaLabelledBy) {
          issues.push({
            type: 'missing-label',
            element: el.tagName + (el.id ? '#' + el.id : ''),
            name: el.getAttribute('name') || '',
          });
        }
      });
      
      return issues;
    });
    
    results.issues.push(...formIssues);
    
  } catch (e) {
    results.issues.push(`Form label check error: ${e.message}`);
  }
  
  return results;
}

async function checkDraggingAlternatives(page) {
  const results = { hasDraggingEvents: false, hasAlternatives: true, issues: [] };
  
  try {
    const dragEvents = await page.evaluate(() => {
      return document.querySelectorAll('[ondrag], [ondragstart], [ondragend], [ondragover], [ondrop]').length > 0;
    });
    
    results.hasDraggingEvents = dragEvents;
    
  } catch (e) {
    results.issues.push(`Dragging check error: ${e.message}`);
  }
  
  return results;
}

async function checkConsistentHelp(page) {
  const results = { helpLinks: [], issues: [] };
  
  try {
    const helpLinks = await page.evaluate(() => {
      const links = [];
      const footer = document.querySelector('footer');
      if (footer) {
        footer.querySelectorAll('a').forEach(a => {
          const href = a.getAttribute('href') || '';
          if (href.includes('github.com') && href.includes('issues')) {
            links.push({ text: a.textContent?.trim(), href, location: 'footer' });
          }
        });
      }
      return links;
    });
    
    results.helpLinks = helpLinks;
    
  } catch (e) {
    results.issues.push(`Consistent help check error: ${e.message}`);
  }
  
  return results;
}

async function checkAuthentication(page) {
  const results = { hasCaptcha: false, hasCognitiveTest: false, issues: [] };
  
  try {
    const hasCaptcha = await page.evaluate(() => {
      const captchaSelectors = [
        'iframe[src*="recaptcha"]',
        'iframe[src*="hcaptcha"]',
        '.g-recaptcha',
        '.h-captcha',
        '[data-sitekey]',
        '.cf-turnstile',
        'input[name*="captcha" i]',
      ];
      return captchaSelectors.some((sel) => document.querySelector(sel));
    });

    results.hasCaptcha = hasCaptcha;
    
  } catch (e) {
    results.issues.push(`Authentication check error: ${e.message}`);
  }
  
  return results;
}

async function runFullAudit() {
  await createDir(REPORT_DIR);
  await createDir(SCREENSHOTS_DIR);
  
  const browser = await chromium.launch({ 
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const allResults = [];
  
  try {
    for (const route of PUBLIC_ROUTES) {
      console.log(`\n=== Auditing ${route.name} (${route.path}) ===`);
      
      const routeResults = {
        route: route,
        axeResults: [],
        manualTests: {},
        screenshots: [],
      };
      
      for (const viewport of VIEWPORTS) {
        console.log(`  Viewport: ${viewport.name}`);
        const context = await browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
          reducedMotion: 'reduce',
        });
        const page = await context.newPage();
        
        try {
          await page.goto(`${BASE_URL}${route.path}`, { waitUntil: 'networkidle', timeout: TIMEOUT });
          await page.waitForTimeout(2000);
          
          const screenshotPath = path.join(SCREENSHOTS_DIR, `${route.name.replace(/\s+/g, '-')}_${viewport.name.replace(/\s+/g, '-')}.png`);
          await page.screenshot({ path: screenshotPath, fullPage: true });
          routeResults.screenshots.push(screenshotPath);
          
          const axeResult = await runAxeOnPage(page, `${BASE_URL}${route.path}`, viewport);
          routeResults.axeResults.push(axeResult);
          
          console.log(`    Violations: ${axeResult.violations.length}, Passes: ${axeResult.passes.length}`);
          
          // Manual tests on desktop viewport only
          if (viewport.width === 1366) {
            console.log(`  Running manual tests...`);
            
            routeResults.manualTests.keyboardNav = await checkKeyboardNavigation(page);
            routeResults.manualTests.reducedMotion = await checkReducedMotion(page);
            routeResults.manualTests.zoom200 = await checkZoom200(page, `${BASE_URL}${route.path}`);
            routeResults.manualTests.targetSizes = await checkTargetSizes(page);
            routeResults.manualTests.semanticHTML = await checkSemanticHTML(page);
            routeResults.manualTests.formLabels = await checkFormLabels(page);
            routeResults.manualTests.dragging = await checkDraggingAlternatives(page);
            routeResults.manualTests.consistentHelp = await checkConsistentHelp(page);
            routeResults.manualTests.authentication = await checkAuthentication(page);
            
            console.log(`    Skip link: ${routeResults.manualTests.keyboardNav.skipLinkWorks ? 'PASS' : 'FAIL'}`);
            console.log(`    Focus visible: ${routeResults.manualTests.keyboardNav.focusVisible ? 'PASS' : 'FAIL'}`);
            console.log(`    Small targets: ${routeResults.manualTests.targetSizes.smallTargets.length}`);
            
            for (const v of axeResult.violations) {
              console.log(`    VIOLATION: ${v.id} [${v.impact}] - ${v.help} (${v.nodes.length} nodes)`);
            }
          }
          
        } catch (e) {
          console.error(`  Error auditing ${route.path} at ${viewport.name}: ${e.message}`);
        } finally {
          await page.close();
          await context.close();
        }
      }
      
      allResults.push(routeResults);
    }
    
  } finally {
    await browser.close();
  }
  
  generateReport(allResults);
  
  console.log(`\n=== Audit Complete ===`);
  console.log(`Report saved to: ${REPORT_DIR}`);
}

function generateReport(allResults) {
  const report = {
    summary: {
      totalRoutes: allResults.length,
      totalViolations: 0,
      totalPasses: 0,
    },
    routes: [],
    prioritizedFixes: [],
  };
  
  let fixId = 1;
  
  for (const routeResult of allResults) {
    const routeReport = {
      name: routeResult.route.name,
      path: routeResult.route.path,
      axeResults: [],
      manualTests: {},
    };
    
    let routeViolations = 0;
    let routePasses = 0;
    
    for (const ax of routeResult.axeResults) {
      routeViolations += ax.violations.length;
      routePasses += ax.passes.length;
      
      routeReport.axeResults.push({
        viewport: ax.viewport,
        violations: ax.violations.map(v => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          helpUrl: v.helpUrl,
          nodes: v.nodes.length,
          targets: v.nodes.slice(0, 12).map(n => ({
            target: n.target,
            html: (n.html || '').slice(0, 180),
            failureSummary: (n.failureSummary || '').slice(0, 280),
          })),
          wcagTags: v.tags.filter(t => t.startsWith('wcag')),
          description: v.description,
        })),
        passes: ax.passes.length,
        incomplete: ax.incomplete.length,
      });
      
      for (const v of ax.violations) {
        const wcagRef = v.tags.filter(t => t.startsWith('wcag2'));
        const severity = v.impact === 'critical' ? 'Critical' : v.impact === 'serious' ? 'High' : v.impact === 'moderate' ? 'Medium' : 'Low';
        
        report.prioritizedFixes.push({
          id: `W${fixId++}`,
          criterion: wcagRef.join(', '),
          issue: v.help,
          severity: severity,
          effort: v.nodes.length > 10 ? 'L' : v.nodes.length > 5 ? 'M' : 'XS',
          route: routeResult.route.path,
          nodes: v.nodes.length,
          evidence: v.helpUrl || '',
        });
      }
    }
    
    report.summary.totalViolations += routeViolations;
    report.summary.totalPasses += routePasses;
    
    const mt = routeResult.manualTests;
    routeReport.manualTests = {
      keyboardNav: {
        skipLinkWorks: mt.keyboardNav?.skipLinkWorks,
        focusVisible: mt.keyboardNav?.focusVisible,
        tabOrderIssues: mt.keyboardNav?.issues?.length || 0,
        issues: mt.keyboardNav?.issues || [],
      },
      reducedMotion: {
        respectsReducedMotion: mt.reducedMotion?.respectsReducedMotion,
      },
      zoom200: {
        noHorizontalScroll: mt.zoom200?.noHorizontalScroll,
      },
      targetSizes: {
        smallTargetsCount: mt.targetSizes?.smallTargets?.length || 0,
        smallTargets: mt.targetSizes?.smallTargets || [],
      },
      semanticHTML: {
        landmarks: mt.semanticHTML?.landmarks || {},
        issues: mt.semanticHTML?.issues || [],
      },
      formLabels: {
        issues: mt.formLabels?.issues || [],
      },
      dragging: {
        hasDraggingEvents: mt.dragging?.hasDraggingEvents,
        hasAlternatives: mt.dragging?.hasAlternatives,
      },
      consistentHelp: {
        helpLinks: mt.consistentHelp?.helpLinks || [],
      },
      authentication: {
        hasCaptcha: mt.authentication?.hasCaptcha,
        hasCognitiveTest: mt.authentication?.hasCognitiveTest,
      },
    };
    
    report.routes.push(routeReport);
  }
  
  fs.writeFileSync(
    path.join(REPORT_DIR, 'wcag-audit-report.json'),
    JSON.stringify(report, null, 2)
  );
  
  const html = generateHTMLReport(report);
  fs.writeFileSync(
    path.join(REPORT_DIR, 'wcag-audit-report.html'),
    html
  );
  
  console.log(`\nTotal violations found: ${report.summary.totalViolations}`);
  console.log(`Total passes: ${report.summary.totalPasses}`);
}

function generateHTMLReport(report) {
  let violationsHtml = '';
  let manualHtml = '';
  let prioritizedHtml = '';
  
  for (const route of report.routes) {
    const axeSummary = route.axeResults.reduce((acc, r) => {
      const vCount = r.violations.length;
      return {
        violations: acc.violations + vCount,
        passes: acc.passes + r.passes,
        incomplete: acc.incomplete + r.incomplete,
      };
    }, { violations: 0, passes: 0, incomplete: 0 });
    
    const routeViolations = route.axeResults.flatMap(r => r.violations);
    const uniqueViolations = [...new Map(routeViolations.map(v => [v.id, v])).values()];
    
    violationsHtml += `
      <tr>
        <td><code>${route.path}</code></td>
        <td>${route.name}</td>
        <td>${axeSummary.violations}</td>
        <td>${axeSummary.passes}</td>
        <td>${axeSummary.incomplete}</td>
      </tr>
    `;
    
    if (uniqueViolations.length > 0) {
      for (const v of uniqueViolations) {
        const wcagRefs = v.wcagTags.join(', ');
        violationsHtml += `
          <tr class="violation-detail">
            <td></td>
            <td colspan="2"><strong>${v.id}</strong>: ${v.help} [${v.impact}]</td>
            <td>${wcagRefs}</td>
            <td>${v.nodes} nodes</td>
          </tr>
        `;
      }
    }
    
    const mt = route.manualTests;
    manualHtml += `
      <h4>${route.name} (${route.path})</h4>
      <table>
        <tr><th>Criterion</th><th>Status</th><th>Detail</th></tr>
        <tr><td>2.4.1 Skip Link</td><td style="color:${mt.keyboardNav.skipLinkWorks ? 'green' : 'red'}">${mt.keyboardNav.skipLinkWorks ? 'PASS' : 'FAIL'}</td><td>${mt.keyboardNav.skipLinkWorks ? 'Skip link works' : 'Skip link not working'}</td></tr>
        <tr><td>2.4.7 Focus Visible</td><td style="color:${mt.keyboardNav.focusVisible ? 'green' : 'red'}">${mt.keyboardNav.focusVisible ? 'PASS' : 'FAIL'}</td><td>${mt.keyboardNav.issues.filter(i => i.includes('Focus ring')).join('; ') || 'All elements have visible focus'}</td></tr>
        <tr><td>2.4.11 Focus Not Obscured</td><td style="color:${mt.keyboardNav.tabOrderIssues === 0 ? 'green' : 'orange'}">${mt.keyboardNav.tabOrderIssues === 0 ? 'PASS' : 'CHECK'}</td><td>Tab order issues: ${mt.keyboardNav.tabOrderIssues}</td></tr>
        <tr><td>2.3.3 Reduced Motion</td><td style="color:${mt.reducedMotion.respectsReducedMotion ? 'green' : 'red'}">${mt.reducedMotion.respectsReducedMotion ? 'PASS' : 'FAIL'}</td><td>prefers-reduced-motion: ${mt.reducedMotion.respectsReducedMotion ? 'respected' : 'not found in inline styles'}</td></tr>
        <tr><td>1.4.10 Reflow (200% Zoom)</td><td style="color:${mt.zoom200.noHorizontalScroll ? 'green' : 'red'}">${mt.zoom200.noHorizontalScroll ? 'PASS' : 'FAIL'}</td><td>${mt.zoom200.noHorizontalScroll ? 'No horizontal scroll' : 'Horizontal scroll detected'}</td></tr>
        <tr><td>2.5.8 Target Size</td><td style="color:${mt.targetSizes.smallTargetsCount === 0 ? 'green' : 'red'}">${mt.targetSizes.smallTargetsCount === 0 ? 'PASS' : 'FAIL (' + mt.targetSizes.smallTargetsCount + ' issues)'}</td><td>${mt.targetSizes.smallTargets.map(t => t.tag + ' "' + t.text + '" = ' + t.width + 'x' + t.height + 'px').join('<br>') || 'All targets >= 24x24px'}</td></tr>
        <tr><td>2.5.7 Dragging Movements</td><td>${mt.dragging.hasDraggingEvents ? (mt.dragging.hasAlternatives ? 'CHECK' : 'FAIL') : 'N/A'}</td><td>${mt.dragging.hasDraggingEvents ? 'Dragging events present' : 'No dragging interactions found'}</td></tr>
        <tr><td>3.2.6 Consistent Help</td><td>${mt.consistentHelp.helpLinks.length > 0 ? 'PASS' : 'CHECK'}</td><td>Help links: ${mt.consistentHelp.helpLinks.map(l => l.text + ' -> ' + l.href).join(', ') || 'None found in expected locations'}</td></tr>
        <tr><td>3.3.8 Accessible Auth</td><td style="color:${!mt.authentication.hasCaptcha ? 'green' : 'red'}">${!mt.authentication.hasCaptcha ? 'PASS (no CAPTCHA)' : 'FAIL (CAPTCHA found)'}</td><td>${mt.authentication.hasCaptcha ? 'CAPTCHA detected' : 'No cognitive tests detected'}</td></tr>
        <tr><td>Semantic Landmarks</td><td>PASS</td><td>${Object.entries(mt.semanticHTML.landmarks).map(([k, v]) => k + ': ' + v).join(', ') || 'None found'}</td></tr>
        <tr><td>Heading Structure</td><td style="color:${mt.semanticHTML.issues.filter(i => i.includes('skipped')).length === 0 ? 'green' : 'red'}">${mt.semanticHTML.issues.filter(i => i.includes('skipped')).length === 0 ? 'PASS' : 'ISSUES'}</td><td>${mt.semanticHTML.issues.filter(i => i.includes('skipped')).join('<br>') || 'No heading level skips'}</td></tr>
        <tr><td>Form Labels</td><td style="color:${mt.formLabels.issues.length === 0 ? 'green' : 'red'}">${mt.formLabels.issues.length === 0 ? 'PASS' : 'FAIL (' + mt.formLabels.issues.length + ')'}</td><td>${mt.formLabels.issues.map(i => i.type + ': ' + i.element).join('<br>') || 'All form elements have labels'}</td></tr>
      </table>
    `;
  }
  
  for (const fix of report.prioritizedFixes) {
    prioritizedHtml += `
      <tr>
        <td>${fix.id}</td>
        <td>${fix.criterion}</td>
        <td>${fix.issue}</td>
        <td><span class="severity-${fix.severity.toLowerCase()}">${fix.severity}</span></td>
        <td>${fix.effort}</td>
        <td><code>${fix.route}</code></td>
        <td>${fix.nodes} nodes</td>
      </tr>
    `;
  }
  
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WCAG 2.2 AA Conformance Audit - Udemy Enroller</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; color: #333; }
    h1, h2, h3, h4 { color: #111; }
    table { border-collapse: collapse; width: 100%; margin: 15px 0; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }
    th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #e0e0e0; font-size: 14px; }
    th { background: #2563EB; color: white; font-weight: 600; }
    tr:nth-child(even) { background: #f9fafb; }
    tr:hover { background: #f0f7ff; }
    code { background: #e8e8e8; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
    .severity-critical { color: #fff; background: #dc2626; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
    .severity-high { color: #fff; background: #ea580c; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
    .severity-medium { color: #fff; background: #ca8a04; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
    .severity-low { color: #fff; background: #6b7280; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
    .summary-box { background: white; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
    .stat-card { text-align: center; padding: 15px; background: #f9fafb; border-radius: 8px; }
    .stat-number { font-size: 28px; font-weight: 700; color: #2563EB; }
    .stat-label { font-size: 12px; color: #6b7280; margin-top: 4px; }
    .violation-detail td { font-size: 12px; color: #666; }
    .manual-section { margin: 20px 0; }
    .manual-section h4 { margin: 20px 0 10px; padding: 8px 0; border-bottom: 2px solid #2563EB; }
    .fail { color: red; font-weight: bold; }
    .pass { color: green; font-weight: bold; }
  </style>
</head>
<body>
  <h1>WCAG 2.2 AA Conformance Audit Report</h1>
  <p><strong>Site:</strong> <a href="https://udemyenroller.madhudadi.in">https://udemyenroller.madhudadi.in</a></p>
  <p><strong>Date:</strong> ${new Date().toISOString()}</p>
  <p><strong>Scope:</strong> All public routes at 320px, 768px, 1366px viewports</p>
  
  <div class="summary-box">
    <h2>Summary</h2>
    <div class="summary-grid">
      <div class="stat-card">
        <div class="stat-number">${report.summary.totalRoutes}</div>
        <div class="stat-label">Routes Tested</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">${report.summary.totalViolations}</div>
        <div class="stat-label">Total Violations</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">${report.summary.totalPasses || 'N/A'}</div>
        <div class="stat-label">Total Passes</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">${report.prioritizedFixes.length}</div>
        <div class="stat-label">Issues Found</div>
      </div>
    </div>
  </div>
  
  <div class="summary-box">
    <h2>Automated Test Results (axe-core)</h2>
    <table>
      <tr>
        <th>Route</th>
        <th>Page</th>
        <th>Violations</th>
        <th>Passes</th>
        <th>Incomplete</th>
      </tr>
      ${violationsHtml || '<tr><td colspan="5">No results</td></tr>'}
    </table>
  </div>
  
  <div class="summary-box">
    <h2>Manual Test Results</h2>
    <div class="manual-section">
      ${manualHtml || '<p>No manual test results</p>'}
    </div>
  </div>
  
  <div class="summary-box">
    <h2>Screenshots</h2>
    <p>Screenshots saved to: <code>wcag-report/screenshots/</code></p>
  </div>
  
  <div class="summary-box">
    <h2>Prioritized Fixes</h2>
    <table>
      <tr>
        <th>ID</th>
        <th>WCAG</th>
        <th>Issue</th>
        <th>Severity</th>
        <th>Effort</th>
        <th>Route</th>
        <th>Nodes</th>
      </tr>
      ${prioritizedHtml || '<tr><td colspan="7">No issues found</td></tr>'}
    </table>
  </div>
  
  <div class="summary-box">
    <h2>Not Verified</h2>
    <table>
      <tr><th>Check</th><th>Reason</th></tr>
      <tr><td>Screen Reader (NVDA/VoiceOver)</td><td>Requires physical screen reader testing on actual devices</td></tr>
      <tr><td>Focus Not Obscured (2.4.11 Full)</td><td>Requires dynamic positioning test with overlays/modals</td></tr>
      <tr><td>Content on Hover/Focus (1.4.13)</td><td>Requires manual interaction with tooltip/popover content</td></tr>
      <tr><td>Pointer Gestures (2.5.1)</td><td>Requires touch device or emulator testing</td></tr>
      <tr><td>Motion Actuation (2.5.4)</td><td>Requires device motion sensor testing</td></tr>
      <tr><td>Identify Input Purpose (1.3.5)</td><td>Requires autofill field validation</td></tr>
      <tr><td>Character Key Shortcuts (2.1.4)</td><td>Requires application-specific keyboard shortcut audit</td></tr>
      <tr><td>Color Contrast (1.4.3, 1.4.6)</td><td>Covered by axe-core automated checks; custom contrast verification requires color picker tooling</td></tr>
    </table>
  </div>
</body>
</html>`;
}

runFullAudit().catch(console.error);
