# WCAG accessibility audit notes

**Date:** 2026-07-12 (local lab)  
**Target:** WCAG 2.2 Level AA **as a design target**, not a formal conformance claim  
**Tooling:** axe-core 4.12 via `@axe-core/playwright`, plus light keyboard/structure checks  
**Base URL audited:** `http://127.0.0.1:8000` (local app; re-run against production after deploy)

## Scope

| In scope | Out of scope / incomplete |
|----------|---------------------------|
| Public pages: `/`, `/about`, `/faq`, `/guides`, `/privacy`, `/udemycoupons` | Authenticated dashboard / settings / history (needs session) |
| Viewports 1366×768 and 320×568 | Full zoom-200% matrix every page (spot-checked via prior tooling) |
| axe WCAG 2.0–2.2 A/AA tags | Screen reader end-to-end (NVDA/VoiceOver) |
| Skip link, `lang`, landmarks, single `h1` | Browser-extension popup UI |
| | Formal VPAT / third-party certification |

Automated tools **cannot** prove WCAG conformance. Residual risk remains until manual AT testing and authenticated flows are covered.

## How to re-run

```bash
# App must be listening (e.g. port 8000)
BASE_URL=http://127.0.0.1:8000 npm run audit:wcag

# Or production after deploy
BASE_URL=https://udemyenroller.madhudadi.in npm run audit:wcag
```

Report artifacts: `wcag-report/wcag-audit-report.json` (and screenshots when using the full script).

## Baseline (before this pass)

Historical report in `wcag-report/` showed **~32 violation groups**, mainly:

- **color-contrast** — `text-gray-400` labels; coupon “Free” / struck prices; privacy `<code>`
- **link-in-text-block** — blue links only distinguishable by color (`hover:underline` only)
- **target-size** (WCAG 2.2) — footer links under 24×24px with tight spacing
- **scrollable-region-focusable** — privacy cookie table horizontal scroller

## Fixes applied (this pass)

| Issue | Change |
|-------|--------|
| Low-contrast muted text | Guides meta / FAQ section label → `text-gray-600`; privacy code → `text-gray-800` |
| Coupon price contrast | Struck price `text-gray-600` (no heavy opacity); Free → `text-green-700` |
| Inline links in body text | Always `underline` + darker blue (`text-blue-700`) on home, FAQ, privacy, cookie banner |
| Footer touch targets | `min-h-[24px] py-1.5`, larger row gap, slightly darker link text |
| Privacy table scroller | `tabindex="0"` + `role="region"` + accessible name + focus ring |
| CSS | `npm run build:css` so new utilities are present in minified bundles |

## Results after fixes (local)

| Check | Result |
|-------|--------|
| axe WCAG tags on 6 public routes × 2 viewports | **0 violation groups** |
| Skip link present | Yes on all 6 |
| First Tab focuses skip link | Yes on all 6 (desktop sample) |
| Exactly one `h1` | Yes |
| `html[lang]` | `en` |
| Confirm dialogs | `window.accessibleConfirm` (focus trap, Escape) from optional #21 |

Machine-readable summary written to `wcag-report/wcag-audit-report.json`.

## Authenticated keyboard pass (#23)

**Date:** 2026-07-12 (local)  
**Routes:** `/dashboard`, `/settings`, `/history` with a local session (fake encrypted cookies for UI shell only — no Udemy calls)  
**Artifact:** `wcag-report/keyboard-auth-audit.json`

### Findings fixed

| Issue | Fix |
|-------|-----|
| Confirm flow keyboard | Already good from #21: focus on OK, Tab trap, Escape closes, restores focus to Start / Clear |
| Settings toggles unnamed / nested interactive / &lt;24px | `role="switch"`, `aria-checked`, labelled by description, 24px height; checkbox sibling (not nested) |
| Settings number/text fields missing `for` | Labels wired to `min-rating`, `update-threshold`, proxy, instructor/title inputs |
| Dashboard section tabs | `role="tablist"/"tab"/"tabpanel"`, `aria-selected`, contrast + focus rings |
| Icon-only controls | Settings gear, export/delete, history delete/expand: accessible names |
| History run cards mouse-only | Expand control is a real `button` with `aria-expanded` / `aria-controls` |
| Stats modal | Escape, Tab trap, restore focus |
| Low contrast | Session notes, logout, danger-zone help, empty history, tab inactive text |

### Keyboard smoke results (after fixes)

| Check | Result |
|-------|--------|
| axe on auth pages (WCAG 2.x AA tags) | **0** violations |
| Start Enrollment → confirm → Escape → focus back | Pass |
| Settings switch Enter toggles `aria-checked` + checkbox | Pass |
| Clear All Data confirm Escape | Pass |
| Dashboard section tabs Enter switches panel | Pass |

### Residual

- Full **screen reader** smoke (NVDA/VoiceOver) still not run  
- Re-run axe against **production** after deploy  
- Mobile **nav strip** horizontal scroll still has focusable links  
- Pill checkboxes for sites/languages (if any dynamic markup) should keep labels when edited later  
- Do **not** claim formal WCAG 2.2 AA conformance

## Related product notes

- `humans.txt` already states accessibility **target** WCAG 2.2 AA, not a formal claim.
- CSP still allows `script-src-attr 'unsafe-inline'` for legacy `onclick` handlers (UE-A11Y-001); separate hardening optional.
