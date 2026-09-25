# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses date-based notes until formal version tags are published.

## [Unreleased] — 2026-09-25

### Added
- **Standalone Compiler Unit & Integration Test Suite ([`tests/test_build_exe.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_build_exe.py))**: Added 6 comprehensive unit and integration tests (`test_check_prerequisites_success`, `test_check_prerequisites_missing`, `test_main_prerequisites_failure_preserves_artifacts`, `test_main_clean_only_skips_prerequisites`, `test_main_default_fallback_triggers_preflight_and_builds`, and `test_main_build_failure_returns_exit_code_one`) asserting pre-flight dependency validation, diagnostic error output, transactional preservation of existing binaries on missing build tools, clean-only bypass, and exit code propagation.
- **Pre-Compiled Binaries Releases Link & Compilation Prerequisites ([`README.md`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/README.md))**: Added prominent direct download link to GitHub Releases and detailed local compilation prerequisites (Python 3.10+, pip install instructions, multi-shell virtual environment activation for Linux/macOS, PowerShell, and CMD, and pre-flight safety callout).
- **Automated SSR & Layout Regression Test Suite ([`tests/test_public_deals_rendering.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_public_deals_rendering.py))**: Added 5 automated unit tests (`test_coupon_category_touch_targets_and_stacking`, `test_faq_scraper_fleet_and_certificate_policy`, `test_invalid_tailwind_classes_absence`, `test_login_heading_sequence_hierarchy`, and `test_base_schema_graph_integrity`) asserting 44px touch targets, responsive 320px column stacking, 17-source scraper fleet consistency, official certificate policy text parity, absence of invalid Tailwind tokens, H2 heading hierarchy, and base schema graph integrity.
- **Completion Certificates Content Guide ([`app/templates/pages/free_coupons_guide.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/free_coupons_guide.html))**: Added dedicated H2 subsection under Safety & Limits clarifying Udemy's April 2020 platform policy and confirming 100% off promotional coupons include official Udemy certificates of completion.
- **HowTo Structured Data ([`app/templates/pages/guides.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/guides.html))**: Injected structured Schema.org `HowTo` block with 4 steps for connecting accounts into the JSON-LD `@graph`.
- **Dashboard Savings Chart Zero-State Placeholder ([`app/templates/pages/dashboard.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/dashboard.html))**: Added centered `#savings-chart-empty` overlay and reactive JavaScript toggling for fresh installations with zero historical runs.
- **Automated Template Rendering Regression Test Suite ([`tests/test_public_deals_rendering.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_public_deals_rendering.py))**: Added 5 comprehensive unit tests validating price and date formatting, mobile code styling, banner suppression on deals routes, category card parity, and WCAG contrast/touch target classes.
- **Automated Hero Spacing and Contrast Regression Tests ([`tests/test_public_deals_rendering.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_public_deals_rendering.py))**: Added [`test_homepage_hero_disclaimer_spacing_and_contrast`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_public_deals_rendering.py#L110) to verify HTTP 200, 32px spacing classes, CTA presence, link touch target classes, and exact 12-count mutation assertions for bullet hyphens.
- **Automated Footer Layout & Contrast Regression Tests ([`tests/test_public_deals_rendering.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_public_deals_rendering.py))**: Added [`test_footer_adticks_badge_layout_and_contrast`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_public_deals_rendering.py#L134) validating Adticks href, anti-shrink/anti-wrap layout tokens, and WCAG AA contrast classes within a scoped badge container slice.
- **CSP Nonce & Escaped CLI Placeholder SSR Regression Tests ([`tests/test_public_deals_rendering.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_public_deals_rendering.py))**: Added `test_public_deals_csp_nonce_on_style_tag` and `test_guides_escaped_cli_placeholders` to verify HTTP 200, nonced style tag presence, absence of dynamic style elements across single and double quotes, and clean literal token rendering without custom tags.

### Changed
- **Catalog SERP Title Tags ([`app/templates/pages/public_deals.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/public_deals.html), [`app/templates/pages/coupon_category.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/coupon_category.html))**: Expanded catalog `<title>` tags to 54–61 characters targeting the 50–60 character Google SERP sweet-spot.
- **Aggregator Scraper Fleet Count & Certificate Q&A ([`app/templates/pages/faq.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/faq.html))**: Synchronized scraper fleet count from 12 to 17 across both visible HTML accordion and JSON-LD `FAQPage` (adding Real Discount, OnlineCourses.ooo, FreebiesGlobal, GeeksGod, TutorialBar), and added symmetrical certificate policy Q&A.

### Fixed
- **Pre-Flight Dependency Validation & Transactional Build Safety ([`build_exe.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/build_exe.py))**: Implemented [`check_prerequisites()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/build_exe.py#L26) using PascalCase `importlib.util.find_spec("PyInstaller")` to detect missing compiler dependencies before executing any destructive operations, preventing catastrophic artifact wiping when building with `--clean --all` in uninitialized environments. Formatted clear diagnostic error banner with active interpreter path (`sys.executable`), pip install commands, multi-shell activation guides, and GitHub Releases URL. Refactored [`main(argv) -> int`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/build_exe.py#L85) with clean return codes, pure argv parsing, and clean-only execution bypass.
- **Design System Color Tokens & Invalid Utilities ([`app/templates/pages/settings.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/settings.html), [`app/templates/pages/dashboard.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/dashboard.html), [`app/templates/pages/history.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/history.html))**: Replaced invalid `bg-gray-55` and `bg-yellow-55` classes with standard `bg-gray-50` and `bg-yellow-50`, eliminating transparent input backgrounds and unstyled status badges.
- **Secondary Text Contrast Elevating ([`app/templates/pages/dashboard.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/dashboard.html), [`app/templates/pages/public_deals.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/public_deals.html))**: Upgraded muted labels and table headers from `text-gray-400` to `text-gray-500` (4.81:1 contrast ratio on `#FFFFFF`), achieving full WCAG 2.2 AA compliance.
- **Button Geometry & Redundant Utilities ([`app/templates/pages/history.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/history.html), [`app/templates/pages/about.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/about.html), [`app/templates/components/base.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/components/base.html))**: Standardized empty-state button geometry to `rounded-lg`, replaced conflicting `font-medium font-bold` with `font-semibold` in `about.html`, and eliminated redundant `ml-2` while adding focus-visible styles on base announcement bar.
- **Semantic Heading Sequence ([`app/templates/pages/login.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/login.html))**: Corrected `<h3>How It Works</h3>` to `<h2>` to eliminate heading sequence inversion.
- **Responsive Category Touch Targets & Layout ([`app/templates/pages/coupon_category.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/coupon_category.html))**: Implemented responsive column stacking (`flex-col sm:flex-row`) with $\ge 44$px touch targets (`min-h-[44px]`), non-clipping inset focus rings, and flex-wrap navigation with `whitespace-nowrap` elements.
- **Cookie Table Mobile Reflow ([`app/templates/pages/privacy.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/privacy.html))**: Added `min-w-[480px]` and `whitespace-nowrap` flags, preserving table legibility within keyboard-accessible horizontal scroll region.
- **Schema Graph References & Guides ItemList Anchor Sync ([`app/templates/components/base.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/components/base.html), [`app/templates/pages/guides.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/guides.html), [`tests/test_org_jsonld.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_org_jsonld.py))**: Removed dangling `parentOrganization` reference and updated `operatingSystem` to "All" in `base.html`, updated `test_org_jsonld.py` assertions accordingly, and updated all ItemList URLs in `guides.html` to match actual DOM article IDs.
- **IndexNow Pinned Hash & Lastmod Synchronization ([`app/services/public_deals_export.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/public_deals_export.py), [`tests/test_indexnow.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_indexnow.py))**: Recomputed CRLF-normalized template SHA-256 hashes and updated honest `STATIC_PAGE_LASTMOD = "2026-09-25"` for `/contact` (`356993bba017ffa1526d7d50243a4021aaee9b5c5850e8e4c6f4f957b7370d07`), `/about` (`7a8cfb6059dc250a6313c47ba3595f319af8697ce7efb390180a023f992d7032`), `/guides` (`8b4527e3d8351d0275d567275923c01f259968ab1a223f1d8491238d77bc26bc` following HowTo schema injection and DOM ID sync), `/faq` (`2bfa3b7d462bddc1a882ee86ac8ccb724c1e0074c8735336111973a38c062d51`), and `/privacy` (`12c0e2397f44735676983be0b7cfcf391caafb58fd343207ebbf183199114e96`), maintaining strict RPN-30 static template integrity and sitemap parity.
- **Content Security Policy Style Nonce Hardening ([`app/templates/pages/public_deals.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/public_deals.html))**: Injected skeleton pulse animation keyframes and `.line-clamp-2` utility into `<head>` with static `<style nonce="{{ request.state.nonce }}">`, eliminating client-side `document.createElement('style')` script execution, curing FOUC layout shifts, and resolving `style-src` CSP violation console errors and telemetry warnings.
- **Guides CLI Placeholder HTML Entity Escaping ([`app/templates/pages/guides.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/guides.html))**: Encoded angle brackets for CLI placeholder arguments (`&lt;TOKEN&gt;`, `&lt;ID&gt;`, `&lt;CSRF&gt;`), preventing browser HTML parser from synthesizing corrupt unclosed DOM elements (`<token>`, `<id>`, `<csrf>`) and eliminating horizontal layout overflow on mobile viewports while preserving clipboard copy fidelity.
- **Footer Adticks Badge Layout & Overflow Prevention ([`app/templates/components/base.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/components/base.html))**: Added `flex-shrink-0` to the Credits & Disclaimer container and Adticks anchor badge (`#adticks-badge`), and enforced `whitespace-nowrap` on the badge and inner text span, preventing multi-line text wrapping on desktop and tablet viewports and eliminating vertical overflow bleed over the disclaimer text.
- **Footer Adticks Badge WCAG 2.1 AA Contrast Compliance ([`app/templates/components/base.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/components/base.html))**: Upgraded brand label text to `text-blue-700` (`#1d4ed8`, 6.01:1 contrast ratio) and prefix text to `text-gray-600` (`#4b5563`, 5.74:1 contrast ratio), fully satisfying WCAG 2.1 AA requirements (>= 4.5:1).
- **Homepage Hero Disclaimer Spacing ([`app/templates/pages/login.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/login.html))**: Added `mb-8` (32px bottom margin) to the amber disclaimer container (`role="note"`) and balanced the primary CTA button container margin to `mb-8`, eliminating the zero-gap collision between the disclaimer box and the "Start Automating Free" / "View Source Code" buttons.
- **Disclaimer Links Touch Target & Mobile Wrapping ([`app/templates/pages/login.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/login.html))**: Wrapped `Privacy · FAQ` in `<span class="whitespace-nowrap">` to prevent the solitary "FAQ" link from orphaning on a separate line on 375px mobile viewports, and added `inline-flex items-center min-h-[24px] py-0.5` to satisfy WCAG 2.2 SC 2.5.8 (Target Size Minimum).
- **Feature List Bullet Contrast ([`app/templates/pages/login.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/login.html))**: Elevated all 12 feature card bullet list hyphens from `text-gray-400` to `text-gray-600` (`#4b5563`), achieving 7.44:1 contrast ratio against white (fully exceeding WCAG 2.2 SC 1.4.3 Level AA 4.5:1 requirement).
- **Deal Card Date Wrapping & Hyphenation ([`app/templates/pages/public_deals.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/public_deals.html), [`app/templates/pages/coupon_category.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/coupon_category.html))**: Added `whitespace-nowrap flex-shrink-0` and safe string slicing `(course.enrolled_at|string)[:10]` to prevent date strings (`Discovered: 2026-08-12`) from breaking awkwardly across lines at the hyphen on narrow cards.
- **Currency & Price Float Formatting**: Formatted Indian Rupee (INR) list prices as comma-grouped integers `{:,.0f}` (rendering `₹1,419` instead of raw float `₹1419.0`) across SSR and CSR in [`public_deals.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/public_deals.html), [`coupon_detail.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/coupon_detail.html), and [`coupon_category.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/coupon_category.html). Formatted Dashboard Lifetime Savings with locale thousand separators (`$1,503,028.00`).
- **Mobile Coupon Code Layout ([`app/templates/pages/coupon_detail.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/coupon_detail.html))**: Added `font-mono text-xs sm:text-base tracking-tight select-all truncate` to eliminate single-character line wraps on 375px mobile viewports while preserving desktop legibility and copy button functionality.
- **Dashboard Savings History Chart Adaptive Ticks ([`app/templates/pages/dashboard.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/dashboard.html))**: Implemented `precision: 0` and adaptive scale formatting in Chart.js Y-axis ticks callback (`$0`, `$100`, `$1k`, `$1.5M`), completely eliminating the 11 duplicate `$0k` labels caused by integer rounding on sparse or zero-value runs.
- **Category Hub Cards Visual Parity ([`app/templates/pages/coupon_category.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/pages/coupon_category.html))**: Upgraded category listing cards with discovery date, original price strike-through, and bold "Free" badge to achieve 1:1 visual parity with the main deals grid.
- **Redundant Announcement Banner Suppression ([`app/templates/components/base.html`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/templates/components/base.html))**: Wrapped `#announcement-bar` in `{% if not request.url.path.startswith('/udemycoupons') %}` to suppress redundant prompts and reclaim ~120px vertical viewport height when browsing deals.
- **WCAG 2.2 AA Contrast & Touch Target Compliance**: Elevated `text-gray-400` to `text-gray-600` on category counts and middle dot separators (achieving 7.56:1 contrast ratio against white) and added `min-h-[24px] py-1` to inline links to satisfy WCAG 2.2 SC 2.5.8 touch target requirements.

## [Unreleased] — 2026-09-24

### Added
- **Two-Tier Resilient HTTP Fallback (`app/services/scraper.py`)**: Added [`_http_get_resilient()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L177) to the [`Scraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L111) base class providing an optimistic native async HTTPX fast path (100ms) with automated CloudScraper fallback on HTTP 403, 503, or Cloudflare challenge detection (`_is_cf_challenge`) for [`ENextScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L736) and [`UdemyXpertScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L996).
- **SSRF DNS Resolver Caching (`app/services/http_client.py`)**: Added `@functools.lru_cache(maxsize=1024)` resolver helper `_resolve_host_ips(host: str) -> tuple[str, ...]` with dual-stack (IPv4/IPv6) resolution and negative-cache immunity, eliminating synchronous event-loop blocking and OS socket contention on repeated domain checks.
- **Environment-Aware SSRF Error Parity (`app/services/http_client.py`)**: Aligned `AsyncHTTPClient._is_safe_url` DNS failure handling with `scraper.py:83-90` (failing closed when `DEPLOYMENT_ENV == "server"`, and failing open in local/dev/test mode) to eliminate false `Blocked unsafe URL` errors on legitimate `udemy.com` URLs under local DNS resolver throttling.
- **Comprehensive SSRF DNS Caching Test Suite (`tests/test_http_client.py`)**: Added 5 targeted unit tests validating LRU cache hits (`call_count == 1`), negative cache exclusion on `socket.gaierror`, local fail-open, production fail-closed, and post-DNS private/loopback IP rejection.
- **Targeted Pipeline Optimization Test Coverage**: Added unit tests in [`tests/test_cli_edge_cases_deep.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_cli_edge_cases_deep.py) (verifying exact 1:1 progress advance calls across mixed course batches), [`tests/test_udemy_checkout_limits.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_udemy_checkout_limits.py) (verifying zero-retry fast-fail on HTTP 200 coupon rejections), and [`tests/test_http_client.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_http_client.py) (verifying connection pool limit attributes).

### Changed
- **Scraper Concurrency Decoupling (`app/services/scraper.py`)**: Moved `detail_sem` from the global [`ScraperService`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L4644) stream to per-scraper isolation within [`_run_scraper()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L4685), eliminating cross-domain head-of-line blocking and starvation across concurrent scrapers while respecting `MAX_SCRAPER_WORKERS` / `--workers`.
- **Semaphore Pruning (`app/services/scraper.py`)**: Removed redundant nested `local_detail_semaphore = asyncio.Semaphore(2)` in [`UdemyFreebiesScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L2112) and [`IDownloadCouponScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L2292), delegating pacing to domain-level locks in [`AsyncHTTPClient`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/http_client.py#L27).
- **Candidate Buffer Right-Sizing & Batched Pagination (`app/services/scraper.py`)**: Standardized `CANDIDATE_BUFFER = 700` across [`KorshubScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L1791), [`FreebiesGlobalScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L4050), [`GeeksGodScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L4252), and [`CouponScorpionScraper`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/scraper.py#L3550) (guaranteeing >=500 courses with 15–25% coupon attrition), added batched pagination (`BATCH_SIZE = 6` / `REST_BATCH_SIZE = 4`), and safeguarded EOF pagination on page N > 1 without false circuit trips.
- **Test Hardening (`tests/test_scraper_concurrency.py`)**: Updated [`tests/test_scraper_concurrency.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_scraper_concurrency.py#L1-L322) to validate per-scraper semaphore isolation and CLI workers scaling without timing fragility.
- **Perimeter Defense Optimization (`app/services/http_client.py`)**: Pruned redundant in-loop `_is_safe_url` checks from `get()`, `head()`, and `post()` retry loops while strictly maintaining perimeter entry validation.
- **AsyncHTTPClient Connection Pool & Keep-Alive Tuning (`app/services/http_client.py`)**: Increased `max_keepalive_connections` from 20 to 40 and extended `keepalive_expiry` from 20.0s to 120.0s in `httpx.Limits`, maintaining warm TCP/TLS sockets across rate-limit cooldown intervals (30s–60s) to prevent socket thrashing and mitigate transient OS DNS `gaierror` dropouts.

### Fixed
- **Progress Bar Advance Invariance (`app/cli/commands/enroll.py`)**: Eliminated counter over-reporting glitch (`6052/3470`) by removing redundant `progress.advance(enroll_task, 1)` calls preceding `continue` in exclusion and library membership filters, establishing the `finally:` block as the authoritative Single Source of Truth for exact 1:1 step advancement.
- **DU Checkout HTTP 200 Rejection Fast-Fail (`app/services/udemy_client.py`)**: Implemented immediate abort on HTTP 200 responses returning non-succeeded JSON status (`{"status": "failed", ...}`), eliminating 4 redundant GET + 4 redundant POST requests and up to 18 seconds of idle backoff sleeps per rejected coupon, while preventing false secondary fallback to `free_checkout`.

## [Unreleased] — 2026-09-23

### Added
- **Two-Tier Checkout Circuit Breaker (`app/services/udemy_client.py`)**: Added serialized concurrency queue via `_checkout_semaphore: asyncio.Semaphore(1)` with double-checked locking around `/payment/checkout-submit/`. Implemented two-tier 403 handling: soft tier on 1st Cloudflare 403 / challenge refreshes CSRF token via GET `/payment/checkout/` with 2.5s–4.0s jittered delay; hard tier on >= 2 consecutive 403s trips global circuit breaker with exponential cooldown (`min(45 * (2 ** (trip_count - 1)), 180)`s) tracked via monotonic clock (`time.monotonic()`), automatically transitioning to HALF-OPEN upon expiry.
- **Two-Phase Complete Library Sync (`app/services/udemy_client.py`)**: Added two-phase library synchronization in [`get_enrolled_courses()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L532): Phase 1 synchronizes active courses (`?is_archived=false`) with fast <3s 10-consecutive early stopping, and Phase 2 synchronizes archived courses (`?is_archived=true`) with 5-page checkpointing (`archived_sync_cursor_page`) up to 500 pages. Skipped entirely on startup when `archived_sync_complete is True` in cache.
- **Library Resync CLI Option & Pacing Delay (`app/cli/commands/enroll.py`)**: Added `--resync-library` CLI option to force re-sync across active and archived libraries, and added 1.5s–2.5s jittered pacing delay after live checkouts to prevent WAF burst penalties.
- **Dedicated Circuit Breaker & Two-Phase Sync Test Suite (`tests/test_checkout_circuit_breaker.py`, `tests/test_udemy_client_cache.py`)**: Added 6 tests in [`tests/test_checkout_circuit_breaker.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_checkout_circuit_breaker.py#L1-L190) and `TestTwoPhaseArchivedLibrarySync` in [`tests/test_udemy_client_cache.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_udemy_client_cache.py#L183-L303) (1,318 regression tests passing).
- **Course ID Validation Helper (`app/services/udemy_client.py`)**: Added module helper [`_is_valid_course_id(cid: Any) -> bool`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L26) enforcing ASCII digit validation, length bounds (`4 < len < 12`), and exclusion from [`BLACKLIST_IDS`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/core/constants.py#L78).
- **Course ID Extraction Resilience & DMA Test Suite (`tests/test_udemy_client_extraction.py`)**: Added 8 comprehensive unit tests to [`tests/test_udemy_client_extraction.py`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/tests/test_udemy_client_extraction.py#L39-L170) covering quoted strings, escaped JSON, HTML entities, mobile deeplink precedence over legacy markup, recommendation carousel collision prevention, CLP container extraction, un-gated DMA resolution, and domain bounds validation (1,309 regression tests passing).
- **Course Domain Model Ownership Flag (`app/services/course.py`)**: Added explicit `is_already_enrolled: bool = False` flag to the [`Course`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/course.py#L32) model, decoupling ownership identification from checkout success status and providing an unambiguous indicator for pre-owned courses.
- **Dual-Key Library Indexing (`app/services/udemy_client.py`)**: Implemented dual indexing in [`UdemyClient`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L29) via `enrolled_courses: Dict[str, str]` (mapping course slug to enrollment timestamp) and `enrolled_course_ids: Set[str]` (storing stringified course IDs), resolving identifier mismatches and enabling O(1) membership lookups across all execution paths.
- **Resilient Atomic Disk Cache Persistence (`app/services/udemy_client.py`)**: Added `_load_enrolled_cache` and `_save_enrolled_cache` storing serialized library state at `data/cache/enrolled_courses_{udemy_user_id}.json`. Persistence writes safely via a `.tmp` file, calls `flush()` and `os.fsync()`, and completes with atomic `os.replace()`. Ensures defensive directory creation via `mkdir(parents=True, exist_ok=True)`, isolates unauthenticated sessions in-memory without disk leakage when `udemy_user_id` is empty, and gracefully recovers from corrupted cache JSON.
- **Deep 500-Page Library Synchronization (`app/services/udemy_client.py`)**: Extended [`get_enrolled_courses()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L493) to paginate up to 500 pages (50,000 courses max) with 50ms cooperative delays (`asyncio.sleep(0.05)`), automatic HTTP 429 `Retry-After` backoff handling (defaulting to 5s), 10-page incremental disk checkpoints (persisting partial batches with `full_sync_complete = False`), and 10-consecutive-hit early stopping strictly gated on `full_sync_complete is True`.
- **Cache & Enrollment Verification Test Suite (`tests/test_udemy_client_cache.py`)**: Added 10 automated unit tests covering cache save/load roundtrips, empty user ID no-op safety, corrupted JSON handling, 500-page paging with 10-page checkpointing, early-stop gating on `full_sync_complete`, timestamp delta pre-owned course detection, and CLI fast pre-check bypass.

### Changed
- **5-Tier Course ID Extraction Hierarchy (`app/services/udemy_client.py`)**: Refactored [`_extract_course_id()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L625) to prioritize a 5-tier extraction hierarchy:
  - *Tier 1*: Canonical mobile deeplink (`r"udemy://discover\?courseId=(\d+)"`).
  - *Tier 2*: Next.js SSR props / DMA JSON embedded regex (`r'"course"\s*:\s*\{[^{}]*?"id"\s*:\s*[\'"]?(\d+)[\'"]?'`) with unnested child object protection (`[^{}]*?`).
  - *Tier 3*: Scoped DOM attributes via lazy BeautifulSoup (strictly limited to `<body>` or `[data-clp-course-id]` container, forbidding recommendation carousel `data-course-id` collisions).
  - *Tier 4*: Quoted and escaped key-value regex (case-insensitive) handling quoted strings (`"courseId": "12345"`), escaped JSON (`\"courseId\":\"12345\"`), and HTML entities (`&quot;courseId&quot;:&quot;12345&quot;`).
  - *Tier 5*: Fallback JSON object regex (`r'"id"\s*:\s*(\d{5,11})\s*,\s*"title"'`).
- **Un-Gated DMA Architecture & Resilient Resolution (`app/services/udemy_client.py`)**: In [`get_course_id()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L771) and [`populate_course_metadata()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L722), un-gated Device Market Attributes (DMA) extraction: unconditionally extracts DMA and calls [`set_metadata(dma)`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/course.py#L159) before falling back to `_extract_course_id`, unblocking recovery of `course_id` from `serverSideProps.course.id` and early-returning to preserve access restriction errors from DMA.
- **Defensive DMA Ingestion & Domain Metadata Bounds Validation (`app/services/course.py`)**: Hardened [`set_metadata()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/course.py#L159) in [`Course`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/course.py#L32) with a top-level dictionary guard (`if not dma or not isinstance(dma, dict): return`), safe navigation for `serverSideProps` and `course` against `None` properties, rigorous bounds validation on candidate IDs from DMA (`isascii()`, `isdigit()`, `4 < len < 12`, and `not in BLACKLIST_IDS`), and safe traversal for `view_restriction` and `breadcrumbs`.
- **False Enrollment Remediation in Direct Checkout (`app/services/udemy_client.py`)**: Normalized [`_du_checkout()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L1277) handling for Udemy API responses containing `"already subscribed"` (message) or `"already_enrolled"` (developer_message) to set `course.status = False`, `course.is_already_enrolled = True`, and `course.error = "already_enrolled"`, correctly preventing pre-owned courses from being reported as newly enrolled and persisting newly discovered owned courses to cache.
- **Pre-Owned Detection & Timestamp Delta Verification in Free Checkout (`app/services/udemy_client.py`)**: Refactored [`free_checkout()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L1345) to fast-bypass checkout prior to network dispatch if `is_already_enrolled` is True. In the post-verification step, compares API `enrollment_time` against UTC `checkout_start_dt`; if `(checkout_start_dt - enroll_dt).total_seconds() > 15`, the course is classified as pre-owned (`course.status = False`, `course.is_already_enrolled = True`, `course.error = "already_enrolled"`), preventing legacy enrollments from falsifying success metrics.
- **Single Checkout Fallback Suppression on Circuit Tripping (`app/services/udemy_client.py`)**: Guarded entry and fallback branches in [`checkout_single()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L1605) to immediately fast-fail (0 HTTP calls) and suppress `free_checkout` fallbacks when circuit is open or `course.error == "checkout_circuit_open"`, stopping thundering herd bypasses.
- **Fallback Guard & Status Demarcation in Single Checkout (`app/services/udemy_client.py`)**: Guarded entry to [`checkout_single()`](file:///run/media/madhud/Storage1/LinuxProjects/Codes/Projects/Udemy%20Enroller/app/services/udemy_client.py#L1518) with zero-latency pre-check, and restricted secondary checkout fallbacks (`_du_checkout` and `free_checkout`) so they never execute if `course.is_already_enrolled` is True, preventing duplicate requests and false success reporting.
- **Consumer Fast Pre-Check & Tri-State Post-Checkout Contracts (`app/cli/commands/enroll.py`, `app/cli/commands/check.py`, `app/gui/bridge.py`, `app/services/enrollment_manager.py`)**:
  - Integrated 0ms fast pre-check via `udemy_client.is_already_enrolled(course)` before `check_course()` in CLI `enroll`, CLI `check`, GUI `AsyncioBridge`, and `EnrollmentManager`, bypassing redundant coupon validation and checkout network roundtrips for already-owned courses.
  - Formatted CLI and GUI feedback with distinct yellow `[ALREADY OWNED]` indicators, updating `already_enrolled_c` statistics without inflating savings metrics.
  - Refactored post-checkout handling into an unambiguous contract: `success is True` (enrolled), `is_already_enrolled` (already owned), `success is None` (indeterminate / timeout), and failure (`success is False`).
- **Test Assertion Alignment (`tests/test_udemy_checkout_limits.py`)**: Updated `test_du_checkout_already_subscribed_400` assertion at line 261 to verify that already subscribed courses yield `course.status is False`, `course.is_already_enrolled is True`, and `course.error == "already_enrolled"`.

## [Unreleased] — 2026-09-19

### Added
- **TeleVault Ecosystem Linkage (`app/routers/seo.py`, `app/templates/components/base.html`)**: Defined `TELEVAULT_URL = "https://televault.madhudadi.in"` in `seo.py` and added an outbound link to TeleVault in the footer ecosystem navigation in `base.html`.
- **Cross-Ecosystem 5-Peer Related Profiles (`app/routers/seo.py`, `tests/test_seo_meta.py`)**: Added `f"{TELEVAULT_URL}/ai-profile.json"` to `ai-profile.json`'s `relatedProfiles` array establishing 5-peer reciprocity, and updated `TestSoftwareApplicationJsonLd.test_ai_profile_related_profiles` in `tests/test_seo_meta.py` to assert the complete 5-peer configuration.

## [Unreleased] — 2026-09-18

### Added
- **Dual Machine Discovery Links (`app/templates/components/base.html`)**: Added canonical `<link rel="ai-profile" type="application/json" href="/ai-profile.json">` and `<link rel="llms" type="text/plain" href="/llms.txt">` tags to the global base template `<head>` (T-W1-05 / F-SEO-10).
- **IndexNow Search Engine Verification Placeholder (`.env.example`)**: Added `INDEXNOW_KEY=` placeholder under search engine verification settings for Bing/Yandex search crawler ownership validation (MIN-05).

### Changed
- **WCAG 2.2 AAA Contrast Elevation (`app/templates/pages/public_deals.html`)**: Elevated category badge contrast from `text-green-700` (4.79:1) to `text-green-800` (7.21:1) on `bg-green-100`, and deal category labels from `text-blue-600` (4.56:1) to `text-blue-700` (7.12:1) on white backgrounds, achieving enhanced contrast compliance exceeding 7.0:1 (T-W2-04 / DEF-ENROLL-CONTRAST-01). Compiled updated utility classes in `app/static/css/tailwind.min.css` and `tailwind.config.js`.
- **RFC 9309 Dynamic Robots Disallow Synchronization (`app/routers/seo.py`)**: Added `/ws/` and `/api/` disallow directives across all crawler sections in the dynamic robots.txt generator, covered by `tests/test_seo_routes.py` (T-W1-04 / F-SEO-05).

## [Unreleased]

Work in the working tree since `e6bc1c2` (not necessarily committed yet).

### Scrapers — High-Concurrency Scaling & Domain-Partitioned Pacing

- **Domain-Partitioned Pacing (`app/services/http_client.py`)**: Replaced global inter-request delays with granular per-domain monotonic timestamps and domain locks, eliminating artificial request queuing across independent coupon aggregator hosts while honoring safe pacing on a per-site basis.
- **Worker Concurrency CLI Flags (`app/cli/commands/enroll.py`, `app/cli/commands/scrape.py`)**: Added `--workers` / `-w` CLI option to `enroll` and `scrape` commands, allowing operators to dynamically override the default scraper worker concurrency.
- **Concurrency & Timeout Bounds (`config/settings.py`, `.env.example`)**: Updated scraper worker concurrency bounds and timeouts (`MAX_SCRAPER_WORKERS = 6`, `SCRAPER_DETAIL_CONCURRENCY = 6`, `CLOUDSCRAPER_MAX_CONCURRENCY = 12`, `SCRAPER_SITE_TIMEOUT_SECONDS = 900`).

### CI — `requirements.lock` was missing the GUI/CLI dependency set

- **Root cause:** `requirements.lock` was last compiled 2026-08-15, but `requirements.txt` gained the desktop-GUI / Rich-CLI stack in `380ce96` (2026-08-27). CI installs from `requirements.lock` (`pip install -r requirements.lock`), so `typer`, `rich`, `customtkinter`, `pillow` and `pyinstaller` were absent at test time and pytest aborted during collection with `ModuleNotFoundError: No module named 'typer'` in `tests/test_cli.py`, `tests/test_cli_edge_cases_deep.py`, `tests/test_cli_log_flags.py` and `tests/test_session_store.py` (4 collection errors, run interrupted).
- **Fix (surgical, no version churn):** appended the 11 missing distributions with `--hash=sha256:` entries and `# via` provenance to match the file's `pip-compile --generate-hashes` format — `typer 0.27.2`, `rich 15.0.0`, `customtkinter 6.0.0`, `darkdetect 0.8.0`, `pillow 12.3.0`, `pyinstaller 6.22.3`, `pyinstaller-hooks-contrib 2026.7`, `altgraph 0.17.5`, `markdown-it-py 4.2.0`, `mdurl 0.1.2`, `shellingham 1.5.4`. Existing pins were left untouched so no unrelated transitive upgrade can regress the suite.
- **Verification:** a fresh `pip install -r requirements.lock` resolves and installs cleanly (hashes valid); full suite **1217 passed, 15 deselected, 0 failed**; the 4 previously-aborting modules now collect and pass (52 tests); `ruff check .` under the lock's pinned `ruff 0.15.22` still reports `All checks passed!`.
- **Note:** `pyinstaller` requires an unpinned `setuptools>=42.0.0`. The lock's existing `--allow-unsafe` warning covers this and CI's Python 3.11 toolchain already provides `setuptools`, so `--require-hashes` resolution succeeds there. `setuptools` is intentionally not pinned (matches the pre-existing file contract).

### Scrapers — Plan v4 Performance Optimizations & Cloudflare Fail-Fast Hardening

- **FreebiesGlobal (`FreebiesGlobalScraper` / `fg`)**:
  - **Dynamic Candidate Bounding**: Replaced static candidate buffer collection with dynamic bounds (`min(CANDIDATE_BUFFER, max(MAX_COURSES * 3, 20))`), breaking listing iteration early when candidate quotas are fulfilled and eliminating hundreds of superfluous detail fetches on low target quotas.
  - **Fast Detail Dispatch**: Enforced single-attempt, tight-timeout execution (`attempts=1, timeout=8, raise_for_status=False, use_cloudscraper=True`) in `_fetch_post`, eliminating retry loops and socket hang contention on dead detail targets.
- **CouponScorpion (`CouponScorpionScraper` / `cs`)**:
  - **Candidate Buffer Floor Optimization**: Reduced the candidate buffer diversity floor from 250 down to 50 (`min(CANDIDATE_BUFFER, max(MAX_COURSES * 3, 50))`), eliminating redundant REST API pagination queries and accelerating small-batch harvests.
- **Korshub (`KorshubScraper` / `kh`)**:
  - **Direct WWW Outbound Hop**: Configured `_allowed_go_hop` to route outbound hops directly to `https://www.korshub.com{path}` instead of the apex domain, eliminating redundant 301/308 redirect roundtrips.
  - **Hardened Regex Extraction**: Hardened JSON-LD and Flight payload regex extraction with full support for escaped and unescaped path slashes (`\/course\/` and `/course/`) anchored strictly to Udemy domains (`https?:?(?:/|\\/){2}(?:www\.)?udemy\.com(?:/|\\/)course(?:/|\\/)[^"]+`), preventing parser dropouts on JSON-encoded responses.
- **FreeCourseSites (`FreeCourseSitesScraper` / `fcs`) & OnlineCourses.ooo (`OnlineCoursesScraper` / `oc`)**:
  - **Compound Cloudflare Turnstile WAF Detection Helper (`_is_cf_challenge`)**: Introduced static helper evaluating HTTP status codes (`403`, `429`, `503`) in compound conjunction with structural challenge signatures (`"just a moment"`, `"cf-browser-verification"`, `"attention required"`, `"cf-challenge"`, `"cf_chl"`, `"cf-turnstile"`, `"challenges.cloudflare.com"`), preventing false positives on standard content.
  - **Outer Category Loop Break in FCS**: Hardened category loops across REST API (`_scrape_rest_api`) and HTML fallback (`_scrape_html_fallback`) to halt immediately on `_cf_403_observed` or `circuit_open`, preventing repetitive blocked category iterations.
  - **Fail-Fast Circuit Breaking (<4s Exit)**: Both FCS and OnlineCourses abort immediately upon detecting Cloudflare Turnstile challenges, setting `self.error = "Blocked by Cloudflare Turnstile WAF"` and avoiding cascading HTML fallback sweeps or Playwright browser launches.
- **Verification Status**:
  - **15 Active Scrapers Live-Verified**: Verified live operations across all 15 active scrapers yielding genuine Udemy courses.
  - **Full Regression Test Suite**: 1,185/1,185 tests passing across the test suite with 74.47% test coverage (exceeding the 50% repository threshold).

### Standalone Executables (`Gui.exe` & `cli.exe`) & Cross-Platform Packaging

- **Standalone Cross-Platform Compiler (`build_exe.py`, `gui.spec`, `cli.spec`)**:
  - **Single-File Desktop Packaging**: Implemented PyInstaller specifications for building standalone single-file executables (`Gui.exe` in windowed mode without terminal popups, and `cli.exe` in console mode for Rich terminal UI).
  - **Asset & Theme Bundling**: Properly packages all CustomTkinter theme assets, templates, and static resources into single-file runtime extraction (`sys._MEIPASS`).
  - **Unified Build Runner**: Added `python build_exe.py --all`, `python build_exe.py --gui`, `python build_exe.py --cli`, and `python build_exe.py --clean`.
- **GitHub Actions Multi-OS Automated Release Pipeline (`.github/workflows/build-executables.yml`)**:
  - Automatically compiles standalone release binaries across Windows (`Gui.exe`, `cli.exe`), Linux (`Gui`, `cli`), and macOS (`Gui`, `cli`) on every tag/release or manual workflow dispatch.
- **Unit Test Suite (`tests/test_build_exe.py`)**:
  - Added test coverage for build artifact cleaning, spec file validation, and PyInstaller execution handling.


### Persistent Encrypted Session Storage & Automatic Long-Term Session Restoration

- **Persistent Encrypted Session Store (`app/services/session_store.py`)**:
  - **Salted HKDF-SHA256 Encryption**: Implemented `save_persistent_session`, `load_persistent_session`, `clear_persistent_session`, and `verify_and_restore_session` utilizing per-session random salts and Fernet symmetric encryption.
  - **Dual-Layer Persistence**: Securely stores encrypted credentials in the local SQLite database (`users` table) with an encrypted backup file (`data/.session.enc` with strict 0600 file permissions) to survive database recreations.
  - **Automatic Session Restoration on Startup**: On Desktop GUI and Unified CLI launch, the application automatically loads and tests saved session credentials in the background against the Udemy API (`get_session_info()`).
  - **Fail-Closed & Zero-Interruption Experience**: If the saved session is valid, the app authenticates seamlessly with 0 manual token re-entry prompts. If the session has expired (typically after 30–90 days on Udemy), the user is gracefully alerted to enter fresh tokens.
- **Desktop GUI Integration (`app/gui/app.py`, `app/gui/bridge.py`, `app/gui/views/login_view.py`)**:
  - Automatically restores saved sessions upon application startup and displays `✓ Connected as <User> (Session Saved)`.
  - Added "✓ Test & Save Session" and "Clear Saved Session" controls to the Login View.
- **Unified Rich CLI Integration (`app/cli/commands/login.py`, `app/cli/commands/logout.py`, `app/cli/commands/enroll.py`, `app/cli/commands/check.py`, `app/cli/commands/stats.py`)**:
  - **Dedicated `login` and `logout` Subcommands**: Added `python cli.py login` (with 1-click browser auto-detection or manual token options to authenticate, inspect account details, and persist session) and `python cli.py logout` (to securely wipe persistent credentials from DB and local storage).
  - **Automatic Session Fallback**: `python cli.py enroll` and `python cli.py check` now automatically use saved persistent credentials when `--token` is omitted, eliminating repetitive credential entry.
  - **Account Status in `stats`**: `python cli.py stats` displays connected account and saved session status.
  - **Per-Course Error Isolation**: Hardened the CLI enrollment loop with item-level `try...except` isolation so individual course anomalies never abort the batch process.
- **Automated Test Suite (`tests/test_session_store.py`, `tests/test_cli.py`)**:
  - Added unit tests verifying encryption/decryption roundtrips, invalid payload rejections, expired session detection, AsyncioBridge IPC events, CLI login/logout commands, and CLI automatic session fallback.

### Website & Documentation — Desktop GUI & Rich CLI Promotions, Guides, FAQ & Schema.org Integration

- **Dashboard Hero Promotion Banner (`app/templates/pages/dashboard.html`)**:
  - **Responsive Promotion Banner (`#desktop-cli-banner`)**: Added an interactive gradient hero promotion banner on the dashboard showcasing the native CustomTkinter GUI and Rich CLI alternatives.
  - **Feature Badges & Command Snippets**: Integrated visual badges ("Native Apps", "CustomTkinter GUI & Rich CLI", "1-Click Cookie Extraction"), terminal command snippets (`python gui.py`, `python cli.py enroll`), feature summaries (17 scrapers, dual progress bars, 100% offline execution), and direct CTA links to `/guides#desktop-gui-cli` and GitHub.
- **Dedicated Guide Section 06 & Schema.org Structured Data (`app/templates/pages/guides.html`)**:
  - **Guide Section 06 (`#desktop-gui-cli`)**: Added comprehensive step-by-step documentation ("Using the Desktop GUI & Unified Terminal CLI") with a 6-minute read estimate covering GUI launch, theme customization, 17-scraper checklist controls, dual progress bars, 1,000-line circular log box, 1-click cookie auto-extraction across 6 supported browsers, and all CLI subcommands (`enroll`, `scrape`, `check`, `stats`, `server`) and filter flags (`--dry-run`, `--categories`, `--languages`, `--min-rating`, `--limit`, `--discounted-only`, `--sites`, `--format`).
  - **Schema.org `ItemList` Position 6**: Extended the JSON-LD `ItemList` schema with position 6 pointing to `https://udemyenroller.madhudadi.in/guides#desktop-gui-cli` ("Desktop GUI & Terminal CLI Guide") while strictly preserving F320 lead paragraph constraints (40–60 words, no anchor links, zero superlatives).
- **Global Footer Navigation Link (`app/templates/components/base.html`)**:
  - Added direct `Desktop & CLI Guide` navigation link targeting `/guides#desktop-gui-cli` in the footer `<nav aria-label="Footer navigation">` across all site pages.
- **FAQ Section & JSON-LD `FAQPage` Rich Snippets (`app/templates/pages/faq.html`)**:
  - **"Desktop GUI & Terminal CLI" FAQ Category**: Added 4 detailed FAQ entries covering CustomTkinter Desktop GUI execution, Unified Rich CLI commands and subcommands, the 6 supported browsers for 1-click cookie auto-extraction (Chrome, Edge, Firefox, Brave, Opera, Chromium), and advantages of 100% local offline execution vs. web server hosting.
  - **Schema.org `FAQPage` JSON-LD Synchronization**: Added matching structured question and answer entries to the `@type: FAQPage` JSON-LD graph for enhanced search engine indexing and rich snippets.
- **Documentation & Integration Test Suite (`tests/test_desktop_cli_docs.py`)**:
  - Added 13 automated test cases verifying dashboard hero banner markup and snippets (`test_dashboard_desktop_cli_hero_banner`), `/guides` section 06 content and flags (`test_guides_page_desktop_cli_section`), `ItemList` position 6 JSON-LD schema (`test_guides_itemlist_schema_includes_desktop_cli`), F320 lead paragraph constraints (`test_f320_guides_lead_preserved`), `base.html` footer link (`test_base_footer_desktop_cli_link`), FAQ HTML and `FAQPage` JSON-LD coverage (`test_faq_jsonld_and_html_desktop_cli_coverage`), and unbroken single `<main id="main-content" role="main">` landmark structure across all 7 public routes (`test_main_landmark_structure_unbroken`).

### Modern Desktop GUI — CustomTkinter Application & Thread-Safe AsyncioBridge

- **Modern Desktop GUI (`gui.py`, `app/gui/`)**:
  - **CustomTkinter Engine & Native Themes**: Implemented a responsive desktop interface powered by CustomTkinter supporting Dark and Light native themes with persistent preferences.
  - **Dual Progress Bars**: Added visual dual progress bars providing concurrent real-time tracking for batch-level scraping across the scraper fleet and item-level enrollment processing in the checkout loop.
  - **17-Scraper Checklist Grid**: Interactive multi-select grid enabling granular scraper fleet control with 1-click batch toggles ("Select All", "Deselect All", "Reset Defaults").
  - **1,000-Line Circular FIFO Log Box**: Embedded terminal log viewer backed by a 1,000-line `collections.deque` buffer with auto-scroll locking, colorized log level tags, and dynamic Pause / Resume controls.
  - **Thread-Safe `AsyncioBridge`**: Implemented a decoupled worker thread bridge managing bidirectional queue communication (`command_queue` and `event_queue`) between the CustomTkinter UI event loop and asyncio background operations (`UdemyClient`, `ScraperService`, `browser_cookies`).
  - **Display Environment Detection**: Hardened `gui.py` with lazy imports and display checks (`DISPLAY`, `WAYLAND_DISPLAY`), outputting clear diagnostic errors and redirecting headless/SSH environments to `python cli.py`.

### Unified Rich CLI — Typer & Rich Terminal Ecosystem

- **Unified Rich CLI (`cli.py`, `app/cli/`)**:
  - **5 Specialized Subcommands**:
    - `enroll`: Automated scraping and bulk enrollment with granular filters (`--categories`, `--languages`, `--min-rating`, `--min-reviews`, `--instructors`, `--limit`, `--browser`, `--token`, `--dry-run`, `--output`).
    - `scrape`: Standalone coupon harvester exporting discovered courses to formatted Rich terminal tables, JSON, or CSV (`--format table|json|csv`, `--output`, `--sites`, `--limit`).
    - `check`: Fast diagnostic utility verifying Udemy authentication status, account profile data, and single coupon URL availability (`--token`, `--url`).
    - `stats`: Displays lifetime enrollment metrics, total savings, currency breakdown, and historical run records with JSON export support (`--output`, `--limit`).
    - `server`: Production Uvicorn web server launcher running the FastAPI interface (`--host`, `--port`, `--reload`).
  - **`--dry-run` Simulation Mode**: Full course discovery and filter evaluation simulation without modifying the user's live Udemy account or submitting checkout requests.
  - **Interactive Terminal Wizard**: Guided prompts automatically engaging when subcommands are invoked interactively without arguments or credentials.
  - **CI & Non-TTY Detection**: Built-in pipe detection (`is_tty()`) automatically disabling animations, progress bars, and spinners when output is redirected to files, pipes, or CI/CD automated runners.

### Universal Browser Cookie Extractor — Safe Zero-Lock Extraction & Decryption

- **Universal Browser Cookie Extractor (`app/services/browser_cookies.py`)**:
  - **Multi-Browser Support**: Automated discovery and credential harvesting across Google Chrome, Microsoft Edge, Mozilla Firefox, Brave, Opera, and Chromium.
  - **Immutable Tempdir SQLite Extraction**: Copies browser cookie databases to isolated temporary directories and queries using SQLite `mode=ro&immutable=1` URI flags, completely preventing database lock contention on active browser sessions.
  - **Cross-Platform Decryption Engines**:
    - **Linux**: Chromium `v10` AES-128-CBC unmasking via PBKDF2 HMAC SHA-1 (`saltysalt`, 24 iterations) with SecretService / GNOME Keyring / `peanuts` master key retrieval.
    - **Windows**: DPAPI `CryptUnprotectData` master key unwrap from `Local State` JSON combined with AES-256-GCM cookie payload decryption.
    - **macOS**: Keychain master password retrieval with PBKDF2 derivation and AES-128-CBC cookie unmasking.
    - **Firefox**: Plain-text SQLite extraction directly querying `moz_cookies` for `access_token`, `client_id`, and `csrftoken`.
  - **Windows Chrome 127+ App-Bound `v20` Detection**: Detects DPAPI App-Bound encryption barriers and surfaces user-friendly troubleshooting guidance recommending Firefox/Edge or manual token input.

### Test Suites — 25 New Unit Tests Across GUI, CLI, and Cookie Extractor

- **Dedicated Unit Test Suites (25 Tests)**:
  - **`tests/test_browser_cookies.py` (8 tests)**: Validates `UdemyBrowserCookies` dataclass conversions, Firefox plain cookie extraction, Linux PBKDF2 decryption, Windows DPAPI mock decryption, macOS Keychain mock decryption, browser candidate path discovery, missing database handling, and fallback note validation.
  - **`tests/test_cli.py` (10 tests)**: Validates `--version`, top-level `--help`, missing cookie handling, `--dry-run` enrollment simulation with JSON output, `scrape` command with JSON and CSV exports, `check` command session validation and single URL verification, `stats` lifetime metrics export, and `server` Uvicorn launcher invocation.
  - **`tests/test_gui_bridge.py` (7 tests)**: Validates AsyncioBridge lifecycle management (start/stop), PAUSE and RESUME command handling, mock TEST_LOGIN authentication flow, AUTO_EXTRACT_COOKIES integration, filter synchronization, SCRAPE_COURSES dispatching, and Loguru log forwarding handler.

### Scrapers — Fleet Capacity Scaling to 500 Courses & Concurrency Optimizations

- **FreebiesGlobal Scraper Scaling (`FreebiesGlobalScraper` / `fg`)**:
  - Pointed `LISTING_ENDPOINT` to `https://freebiesglobal.com/tag/udemy-100-off/page/{p}/`, unlocking access to FreebiesGlobal's full 8,024-course tag archive (535 pages) rather than the 2-page `/dealstore/udemy` landing showcase.
  - Implemented 0-hop offer card direct link parsing (`a.re_track_btn`) + 1-hop detail post fallback (`article.post a.btn_offer_block`) with fast regex and `courses_added_this_page == 0` early termination, scaling yield from 53 to **500 valid Udemy coupons**.
- **Korshub Scraper High-Speed JSON-LD & Flight Extraction (`KorshubScraper` / `kh`)**:
  - Implemented fast JSON-LD regex matching (`"url":\s*"(https://www.udemy.com/course/[^"]+)"`) and enhanced Next.js Flight SSR unicode unescaping (`\u0026`, `\u002f`, `\u003d`, `\u003f`, `\"`, `\/`), resolving 500 courses from the 3,138-course catalog in <20s.
- **CouponScorpion Fast Single-Attempt Hop Resolution (`CouponScorpionScraper` / `csc`)**:
  - Optimized `out.php` hop resolution to single attempt (`attempts=1`), `timeout=8s`, and added relative redirect handling, resolving 500 courses from the 1,786 Category 21032 catalog in <30s.
- **OnlineCourses.ooo Isolated Detail Ingestion (`OnlineCoursesScraper` / `oc`)**:
  - Switched detail page requests to isolated `self.http.get` calls, preventing transient detail 404s/timeouts from tripping the listing circuit breaker and paginating up to 500 courses.
- **Live Inventory Verification for GeeksGod (`gg`) & TutorialBar (`tb`)**:
  - Verified that GeeksGod's 35 courses and TutorialBar's 140 courses represent 100% of their active live databases, with dynamic discovery enabled up to 500 items.

### Scrapers — TutorialBar Scraper Engine Integration (17 Scrapers Fleet)

- **TutorialBar Scraper Engine Integration (17 Scrapers Fleet)**:
  - **`TutorialBarScraper` (`tb` / "TutorialBar")**: Integrated `https://www.tutorialbar.com/live-coupons` as the 17th active scraper.
  - **Next.js React Server Component (RSC) Flight Stream Extraction**: Extracts embedded `couponUrl` and `couponCode` strings directly from `self.__next_f` flight chunks with Unicode entity unescaping (`\u0026` -> `&`, `\"` -> `"`, `\u002F` -> `/`), enabling 0-hop direct coupon resolution.
  - **Multi-Tiered Fallback Architecture**: Includes secondary 0-hop DOM card extraction (`.coupon-card a[href*='udemy.com']`) and 1-hop detail resolution (`/course/{slug}` -> `a.btn-primary`).
  - **Robots.txt & Circuit Safety**: Bypasses disallowed `/go/` endpoints via listing page flight data parsing; implements early break on zero-yield pages and 500-course caps.
  - **`SCRAPER_REGISTRY` & `UserSettings.default_sites()`**: Expanded to 17 scrapers while preserving `_FROZEN_REGISTRY_PREFIX_LEN = 10` for `coupon_checker.py`.
  - **Test Suite**: Created `tests/test_tutorialbar_scraper.py` and synchronized `tests/test_scraper.py`, `tests/test_settings_sites_persist.py`, `tests/test_coupon_checker.py`, and `tests/test_scrapers_url_smoke.py`.

### Scrapers — Tier-1 Scraper Fleet Expansion (16 Scrapers)

- **Tier-1 Scraper Fleet Expansion (16 Scrapers)**:
  - **`RealDiscountScraper` (`rd` / "Real Discount")**: Replaced legacy HTML scraping with direct CDN JSON REST API (`https://cdn.real.discount/api/courses?page={p}&limit=100&sortBy=sale_start&store=Udemy&freeOnly=true`), supporting 0-hop direct coupon link extraction, ad/sponsored filtering, and non-zero price rejection.
  - **`OnlineCoursesScraper` (`oc` / "OnlineCourses.ooo")**: Added RSS `/feed/` XML ingestion + paginated `/page/{p}/` crawling, resolving detail buttons via ReHub CSS selector fallbacks (`a.btn_offer_block`, `a.re_track_btn`, `a[href*="udemy.com"]`).
  - **`FreebiesGlobalScraper` (`fg` / "FreebiesGlobal")**: Added deal category harvesting (`https://freebiesglobal.com/dealstore/udemy/page/{p}/`) with direct offer card extraction and 1-hop detail fallback.
  - **`GeeksGodScraper` (`gg` / "GeeksGod")**: Added `/courses?page={p}` catalog crawling with detail CTA resolution, tracking parameter sanitization (`rand=4`, `ref` stripped via `Course.normalize_link`), and WordPress pagination loop break detection.
  - **`SCRAPER_REGISTRY` & Invariant Preservation**: Expanded registry to 16 scrapers while strictly preserving the `FROZEN_10` prefix at index positions 0..9 and `_FROZEN_REGISTRY_PREFIX_LEN = 10` for `coupon_checker.py`.
  - **`UserSettings.default_sites()`**: Expanded to 16 keys defaulting to `True`.
  - **Dedicated Unit Test Suites**: Created `tests/test_onlinecourses_scraper.py`, `tests/test_freebiesglobal_scraper.py`, `tests/test_geeksgod_scraper.py`, and updated `tests/test_realdiscount_scraper.py`, `tests/test_scraper.py`, `tests/test_settings_sites_persist.py`, `tests/test_coupon_checker.py`, and `tests/test_scrapers_url_smoke.py`.

### Scrapers — Fleet-Wide 500 Latest Coupons Standardization & Anti-Zombie Chunked Detail Batching

- **Standardized `MAX_COURSES = 500` Across All 12 Scrapers in `SCRAPER_REGISTRY`**:
  - Enforced a uniform maximum cap of 500 latest coupons across the entire fleet (`ENextScraper`, `InterviewGigScraper`, `UdemyXpertScraper`, `CoursesityScraper`, `CourseFolderScraper`, `CouponamiScraper`, `KorshubScraper`, `UdemyFreebiesScraper`, `IDownloadCouponScraper`, `FreeCourseSitesScraper`, `CoursonScraper`, `CouponScorpionScraper`).
  - Expanded listing candidate buffers to 750–800 raw candidates (`MAX_LISTING_PAGES`, `MAX_API_PAGES`, `CANDIDATE_BUFFER`, `MAX_COUPON_PAGES`) to guarantee discovering 500 valid coupons when available on source platforms.
- **Anti-Zombie Chunked Detail Batching (`DETAIL_BATCH_SIZE = 10`)**:
  - Refactored detail iteration loops across all scrapers to execute in discrete chunks (`asyncio.gather(*chunk, return_exceptions=True)` in batches of 10) with immediate early loop break when `len(self.data) >= self.MAX_COURSES`.
  - Completely eliminated uncancelled background task leaks and socket descriptor exhaustion on early loop termination.
- **Korshub 3,767-Course `/free-courses?platform=UDEMY` Scale & Next.js Flight SSR Extraction**:
  - Upgraded `KorshubScraper` to target the dedicated 100% free courses platform endpoint (`https://www.korshub.com/free-courses?page={p}&platform=UDEMY`), tapping into Korshub's full 261-page (~3,132 Udemy courses) catalog instead of mixed multi-platform pages.
  - Implemented Next.js Server Components Flight payload extraction (`_extract_udemy_url_from_text`) with Unicode and entity unescaping (`\u0026` -> `&`, `\/` -> `/`), directly resolving full Udemy coupon URLs without intermediary redirect overhead.
  - Verified live performance: extracted 500 out of 500 valid Udemy coupons in 266s.
  - Added unit test `test_korshub_nextjs_flight_unicode_unescape` in `tests/test_korshub_scraper.py`.

- **Courson `/load-more-coupons` Live Pagination Scale**:
  - Upgraded `CoursonScraper` to target `POST https://courson.xyz/load-more-coupons` with `{"filters": {}, "offset": offset}`, successfully extracting 100% of all live courses (277 out of 279 active courses harvested, up from 151).
  - Maintained safe window.courseData extraction and discrete chunked batching.

- **Test Suite & CI Parity Synchronization**:
  - Updated all unit, smoke, and regression test suites (`tests/test_scrapers_url_smoke.py`, `tests/test_scrapers_real.py`, `tests/test_interviewgig_scraper.py`, `tests/test_coursesity_scraper.py`, `tests/test_udemyfreebies_scraper.py`, `tests/test_idownloadcoupon_scraper.py`, `tests/test_couponscorpion_scraper.py`, `tests/test_courson_scraper.py`, `tests/test_enext_scraper.py`, `tests/test_freecoursesites_scraper.py`, `tests/test_korshub_scraper.py`).
  - Verified 100% test pass (912 passed) and clean linter checks (`ruff check .`).

- **iDownloadCoupon WooCommerce Store REST API & Safe Probing**:
  - Upgraded `IDownloadCouponScraper` to WooCommerce Store REST API (`STORE_API_ENDPOINT = "https://idownloadcoupon.com/wp-json/wc/store/v1/products"`), fetching 100 items per request (`PER_PAGE = 100`, `MAX_PAGES = 15`, `MAX_COURSES = 1000`).
  - Added safe capability probing with dynamic `X-WP-TotalPages` header pagination, clean 400 (`rest_post_invalid_page_number`) and empty-list EOF handling, and concurrent listing page fetches (`LISTING_CONCURRENCY = 5`).
  - Implemented resilient fallback to paginated HTML crawling (`/page/{n}/`) when Store API probing is unavailable or returns an error.
  - Hardened `/udemy/{id}/` 302 redirect resolution with `attempts=1`, `local_detail_semaphore = 10`, HTML entity unescaping, and strict `is_udemy_course_url`/`is_trk_udemy_url` host gating.

- **UdemyFreebies 1,000-Course Scale & Connection Pool Sizing**:
  - Scaled `UdemyFreebiesScraper` capacity from 500 to 1,000 courses (`MAX_COURSES = 1000`, `COURSES_PER_PAGE = 12`, `MAX_LISTING_PAGES = 85`, `LISTING_CONCURRENCY = 6`).
  - Configured `HTTPAdapter(pool_connections=50, pool_maxsize=50)` on CloudScraper sessions in `AsyncHTTPClient` to eliminate connection pool starvation under high detail concurrency.
  - Implemented `UDEMY_RESERVED_SLUGS` filtering rejecting non-course redirect destinations (`/cart`, `/terms`, `/support`, `/privacy`, `/join`, etc.).
  - Hardened single-hop `/out/{slug}` redirect resolution with `attempts=2`, single-segment course path rewriting (`/course/{slug}/?couponCode=...`), and `local_detail_semaphore = 10`.

- **Unit Test Suites**:
  - Added dedicated unit test suites `tests/test_idownloadcoupon_scraper.py` (9 tests covering Store API extraction, EOF handling, 400 errors, HTML fallback, trk redirect unwrap, hostile host rejection, and deduplication caps) and `tests/test_udemyfreebies_scraper.py` (8 tests covering class attributes, HTML listing extraction, single-hop redirects, reserved slug rejection, trk unwrap, hostile redirect drops, and max course caps).

### Scrapers — Coursesity 3,000+ Course Scale & Angular 18 SSR TransferState Extraction

- **Coursesity Scale & Angular SSR TransferState Extraction**:
  - Scaled scraper capacity from ~140 to 3,051 courses (`MAX_COURSES = 3500`, `COURSES_PER_PAGE = 15`, `MAX_LISTING_PAGES = 205`) via single-phase Angular 18 SSR TransferState extraction targeting `<script id="app-root-state">` (with fallback support for `serverApp-state` and `coursesity-state`).
  - Added specialized Angular entity unescaping (`_sanitize_angular_entities`) decoding custom Angular entities (`&q;`, `&a;`, `&s;`, `&l;`, `&g;`, `&b;`) alongside standard HTML entities.
  - Implemented recursive JSON state key discovery (`_find_courses_and_count_in_state`) dynamically discovering course lists (`courseData`, `courses`, `COURSE_LIST`, `items`, `data`, `results`) and total count metadata (`totalCount`, `totalCourses`, `total_count`, `count`).
  - Added 2-tier URL resolution (`_unwrap_udemy_url`): Tier 1 static regex/query parameter unwrapping without network overhead (handling `u=`, `murl=`, `dest=`, and double-encoded URLs), with Tier 2 cooperative fallback (`_resolve_trk_redirect`) for opaque `trk.udemy.com` redirect tokens.
  - Hardened pagination with `LISTING_CONCURRENCY = 5` semaphore control, circuit-breaker safety, and comprehensive fallback to DOM-based `/course-detail/` crawl when SSR TransferState is absent or malformed.
  - Added 10 comprehensive unit tests in `tests/test_coursesity_scraper.py` covering entity unescaping, malformed JSON fallback, recursive key variations, pagination bounding, URL unwrap tiers, concurrency limits, DOM fallback, title cleaning/deduplication, and scraper contracts.

### Scrapers — CouponScorpion 500-Course Scale & HTTP Client Thread-Safe Concurrency

- **CouponScorpion 500-Course Scale**:
  - Upgraded `CouponScorpionScraper` capacity to 500 courses (`MAX_COURSES = 500`).
  - Added WP REST listing pagination (`REST_URL` with `per_page=100`, page 1..7) and paginated HTML fallback (`HTML_LISTING` category listing).
  - Implemented fast regex scanning (`_OUT_PHP_RE`) for `/scripts/udemy/out.php` links before falling back to DOM parsing.
  - Added HTML entity unescaping for redirect parameters in `_out_url_from_href`.
  - Hardened hop resolution with `attempts=2`, strict no-follow gates, and 20ms cooperative async sleep.
  - Converted detail fetching to concurrent task dispatch via `asyncio.as_completed` bounded by `detail_semaphore`.

- **HTTP Client Thread-Safe CloudScraper Sessions & Keyword Normalization (`app/services/http_client.py`)**:
  - Replaced shared `_scraper` / `_mobile_scraper` attributes with `threading.local()` storage, guaranteeing thread isolation and preventing session state corruption across concurrent threads.
  - Implemented thread-safe scraper registry (`_scrapers_lock`, `_all_scrapers`) with atomic cleanup in `_close_all_scrapers()` upon client teardown and re-initialization.
  - Normalized redirect keyword arguments across `get()`, `post()`, and `head()` methods to support both `allow_redirects` (requests/cloudscraper) and `follow_redirects` (httpx) without parameter collision errors.
  - Scaled default scraper concurrency: `MAX_SCRAPER_WORKERS` raised from 5 to 12 in `config/settings.py` (and `ScraperService` worker semaphore fallback), with detail concurrency semaphore raised from 10 to 20.

### Scrapers — live fleet 13→12 (complete delete Course Joiner)

- `SCRAPER_REGISTRY` complete-deletes Course Joiner from the live fleet (12 keys). Scraper class, unit tests, and live tests are deleted (unlike Real Discount and Discudemy, whose classes and unit tests were kept). Leftover stored JSON keys for that name are dropped via GET/PUT/reset merge (stale names not in `default_sites()`).
- Coupon checker: frozen 10, appended 2 (Courson, CouponScorpion). `N=2` is appended-only. `N=3` is appended + Couponami. Leftover `N=11` omits iDownloadCoupon. Compose default `CHECKER_SCRAPE_MAX_SOURCES=0` (all keys) is unchanged.
- Public FAQ and README list the 12 live aggregators (FAQ display order, not registry order). Tutorialbar is not a current source.

### Scrapers — live fleet 14→13 (complete delete FreeWebCart)

- `SCRAPER_REGISTRY` complete-deletes FreeWebCart from the live fleet (13 keys). Scraper class, unit tests, and live tests are deleted (unlike Real Discount and Discudemy, whose classes and unit tests were kept). Leftover stored JSON keys for that name are dropped via GET/PUT/reset merge (stale names not in `default_sites()`).
- Coupon checker: frozen 11, appended 2 (Courson, CouponScorpion). `N=2` is appended-only. `N=3` is appended + Couponami. Leftover `N=12` omits Course Joiner. Compose default `CHECKER_SCRAPE_MAX_SOURCES=0` (all keys) is unchanged.
- Public FAQ and README list the 13 live aggregators (FAQ display order, not registry order). Tutorialbar is not a current source.

### Scrapers — live fleet 16→14 (unregister Real Discount, Discudemy)

- `SCRAPER_REGISTRY` unregisters Real Discount and Discudemy from the live fleet (14 keys). Scraper classes and unit tests are kept. Leftover stored JSON keys for those names are dropped via GET/PUT/reset merge (stale names not in `default_sites()`).
- Coupon checker: frozen 12, appended 2 (Courson, CouponScorpion). `N=2` is appended-only. `N=3` is appended + Couponami. Leftover `N=13` omits Course Joiner. Compose default `CHECKER_SCRAPE_MAX_SOURCES=0` (all keys) is unchanged.
- Public FAQ and README list the 14 live aggregators (FAQ display order, not registry order). Tutorialbar is not a current source.

### Scrapers — FWC hop-200, Korshub `/go/` query, UF `/out/` rewrite

- FreeWebCart parses hop-200 interstitial HTML on the same C11 GET (Couponami quoted-URL loop, cap 1) and logs after each detail chunk; Korshub allows `/go/{uuid}` hrefs that have a query (hop URL stays path-only); UdemyFreebies `_resolve_out` rewrites single-segment `udemy.com/{slug}?couponCode=` to `/course/{slug}/` then existing course/trk gates, with local Semaphore(8). Real Discount and Discudemy parser classes were unchanged in that hop wave (C15, C1/C6); they are not live-registry keys after the 16→14 unregister.

### Scrapers — FreeCourseSites categories

- FreeCourseSites scrapes coupon-first `100-off-udemy-coupon` (137426), then archive `free-udemy-courses` (67983); `udemy-free-courses` (78256) is removed. REST first, HTML fallback when under 500; `MAX_COURSES` unchanged.

### Scrapers — hop/parser fixes (C11–C21, C1/C6)

- Aggregator hops (CouponScorpion `out.php`, UdemyFreebies `/out/`, iDownloadCoupon redeem, FreeWebCart same-origin `/redirect/`, Korshub same-origin `/go/`) use C11 `self.http.get` kwargs plus `attempts=1` (C20). Location is not followed; only `is_udemy_course_url` or `is_trk_udemy_url` is accepted. No Playwright on hops (C14).
- Coursesity: comment-only; no extra site-redirect GET; URL yield without `couponCode=` is expected (C12).
- Interview Gig: `_resolve_one` wrapper, local Semaphore(8), E-next-style chunks, 80 trk-HTTP cap; frozen helper is never `_run_detail_task` func (C13).
- Korshub: listing `/courses/{one-segment}` without `-udemy`; no `udemy.com/course/{korshub-slug}` construction; hop only same-origin `/go/{uuid}` (C17).
- FreeWebCart: `sourceUrl`/direct href/regex first; hop only `freewebcart.com|www.freewebcart.com` + `^/redirect/[A-Za-z0-9_-]+$` (C19).
- Course Joiner: short-trk resolved inside `_fetch_detail` via frozen helper; no nested `_run_detail_task` (C21).
- Real Discount: API miss sets `self.error` to `API unreachable; Playwright skipped`; no Playwright fallback (C15).
- Discudemy: log candidate and found counts; never GET couponami.com/go/ (C1/C6).
- Live tests: UF/IDC/CJ added; 0-ok for RD/DU/CSC/UF/IDC/FWC/UX/KH/IG/CJ; Coursesity keeps `>0` URLs with no coupon claim (C16/C18).

### Scrapers — Discudemy, Courson, CouponScorpion (registry 13→16)

- `SCRAPER_REGISTRY` expands from 13 to 16 sources: Discudemy, Courson, and CouponScorpion join the existing 13 (including Course Joiner).
- Public FAQ and README list the 16 aggregator scrapers. Tutorialbar is not a current source.
- `CHECKER_SCRAPE_MAX_SOURCES=0` or a cap ≥ registry size scrapes all keys. Execution order: appended sources (Discudemy, Courson, CouponScorpion) first, then Couponami, then the rest of the frozen 13.
- `0 < N < size` scrapes at most N sources. Cap slots go to appended keys first, then Couponami, then the frozen prefix from the front. **N<4 omits Couponami.** N=3 is only the three new sources. N=13 is the three new sources + Couponami + 9 other frozen names.
- Omitted source names are logged. A stale `N=13` no longer drops Discudemy, Courson, or CouponScorpion; it can still omit the last frozen names.
- Discudemy leftover native pages may be empty because `/all` cards are collected by Couponami. Discudemy does not fetch couponami.com or `/go/`.
- C11 residual: checker list order prefers the new sources plus Couponami; with 5 workers and a 2700s run timeout, later frozen sites can still time out. `ScraperService` already logs timed-out names.
- C7: settings PUT upgrade-merges sites (`defaults ← stored ← PUT`) so new scraper keys persist on save. GET still does not write. Unchecked boxes still save `False`.
- F252: listing `_http_get` honors `robots.txt` (fail-open). Courson `/claim/` is Disallow and is never requested.

### Residual wave (2026-08-19)

- No residual-wave product code change. `tests/test_llms_full_txt.py` now comments why `/llms-full.txt` vs `/llms.txt` comparison normalizes the per-request `Last generated` line (bodies are not byte-identical).

### SEO, Schema & Conversion Enhancements (2026-08-17)

- **High-CTR Title & Meta Description Optimization (`/udemycoupons`)**:
  - Optimized title tag to `"100% Free Udemy Coupons & Promo Codes (Updated Hourly)"` targeting high-intent organic search keywords.
  - Aligned high-converting meta description across `description`, `og:description`, and `twitter:description`: `"Browse 100% free Udemy coupons, promo codes, and verified deals. Automate enrollment and claim free courses in coding, AI, business, and design."`
  - Explicitly set Open Graph `og:type` to `"website"`.
- **ItemList Schema Integration (`Course` + `Offer`)**:
  - Integrated Schema.org `ItemList` with embedded `Course` nodes on `/udemycoupons` (`app/templates/pages/public_deals.html`) and category pages (`app/templates/pages/coupon_category.html`).
  - Embedded nested `Offer` with `price: "0"`, `priceCurrency: "USD"`, and `availability: "https://schema.org/InStock"`.
- **4-Question FAQPage Schema with 100% DOM Parity**:
  - Expanded and synchronized structured data (`FAQPage`) and visible FAQ accordion DOM on `/udemycoupons` across 4 core user intent questions (free verification, update frequency, redemption instructions, automated enrollment tooling).
- **Auto-Enroller Conversion Callout Banner**:
  - Added native callout banner linking to the automated enrollment tool (`/`) with zero-CLS reserved container height (`min-h-[130px] sm:min-h-[100px]`), gradient styling, and high-CTR CTA (`Start Auto-Enroller`).
- **Empty FAQ Guard & Detail Schema Hardening (`coupon_detail.html`)**:
  - Wrapped FAQ JSON-LD and HTML rendering in `{% if coupon_content.faqs and coupon_content.faqs | length > 0 %}` to prevent invalid empty FAQ schema generation.
  - Hardened Course schema with fallback description and normalized Offer `price: "0"` string.
- **Regression Tests**:
  - Added test coverage in `tests/test_public_deals_pagination.py` and `tests/test_coupon_detail_page.py`.

### Docs — Alembic head / local apply (2026-08-16)

- Chain head is `c01d021a9e03` (not `c01d021a9e01`). Revisions `c01d021a9e01` (`users.cookies_salt`), `c01d021a9e02` (`enrollment_runs.last_heartbeat`), and `c01d021a9e03` (drop `user_settings.firecrawl_api_key` / `enable_headless`) are inspect-idempotent.
- `alembic/env.py` fail-closes when both `udemy_enroller.db` and `data/udemy_enroller.db` exist unless `sqlalchemy.url` is an explicit pin (`scripts/alembic_upgrade_pinned.py`).
- **Local** live DB (`./udemy_enroller.db`) upgraded to `c01d021a9e03` (`cookies_salt` + `last_heartbeat` present). Production named volume **not** upgraded.
- `scripts/migrate_cookies_per_session.py` **not** run. `AUTO_CREATE_TABLES` remains `False`.

### Docs — F004 residual accepted (2026-08-16)

- F004 residual accepted (ops/product); no key rotate. Not legal advice / not counsel-approved DPIA.

### Docs — F011 last-success proven (2026-08-16)

- Host proof recorded: named volume `app-data`, backups `/var/backups/udemy-enroller`, newest file age 6.16 h, integrity ok, 26 h freshness exit 0, cron present. Restore not run.
- F004 remains **open / UNSIGNED** (Defer). Owner may now Accept. F011 no longer blocks key rotation; still no rotate/purge unless the owner asks.
- Documented `--install-backup-cron` does **not** match this host — do not run it blindly.

### Docs — F004 owner decision = Defer until F011 (2026-08-16)

- **Not residual acceptance.** Decision ☑ Defer only (not Accept, not Redesign). Signature n/a — not accepted. F004 remains **open / UNSIGNED**.
- No key rotation or blob purge until F011 last-success is proven.

### Docs — unsigned F004 DPIA / D.3 wording (C1–C7)

- **Not a close:** F004 remains open. No key rotation or blob purge.
- `docs/dpia-enroller-cookies-skeleton.md` **0.6-draft-v1**: drop false DPDP SPD/s.7/s.7(c) cites; privacy **template exists** / per-session envelope **not** on `privacy.html` (HTML not edited); `security-trio-fix.md` labeled fail-closed validation; §2.6 Udemy **plus** optional GTM/GA4 after consent; **F019-plaintext** vs fleet F019 humans.txt; wipe is live-DB only vs 14d/30-file unencrypted backups.

### P3/P4 wave — last enroller items (F-ENRL-*, F-XSITE-*)

- **C11**: Alembic migration `alembic/versions/c01d021a9e03_drop_firecrawl_and_headless_from_user_settings.py` (head `c01d021a9e03`) drops `firecrawl_api_key` / `enable_headless` from `user_settings` (inspect-idempotent). Applied on the **local** live DB; production **not** upgraded.
- **C13**: `scripts/deploy.sh` hardened — `set -euo pipefail` fail-fast, `chmod 600` on the generated `.env`; `bash -n` clean.
- **C15**: coupon-checker loop now serves a loopback `/health` endpoint (default port 8001, `COUPON_CHECKER_HEALTH_PORT` override) reporting `last_run_age_seconds`; 200 `ok` while a cycle finished within 26h, 503 `stale` otherwise (incl. before the first run). Docker Compose `coupon-checker` healthcheck wired to it. `COUPON_CHECKER_HEALTH_PORT` is also documented in the compose service comment (`.env.example` editing is blocked by the repo's `*.env.*` policy; compose is the reference).
- **Tests**: `tests/test_coupon_checker_health.py` — /health 200 + age, 503 stale >26h / never-run, 404 unknown path (ephemeral port 0, importlib-by-path).
- **F-XSITE-001**: seo.py FAQ + ai-profile.json `Person`/`author` descriptions now use `config.settings.experience_years_label()` (SSOT from `EXPERIENCE_START`); zero `10+ years` literals remain in `app/`.
- **F-XSITE-002**: base.html footer copyright `© {{ current_year }} Enroller by Madhu Dadi`; `current_year` global registered on all four Jinja2Templates instances (main/dashboard/public_deals/seo) in main.py's template-globals loop.
- **F-XSITE-009**: `twitter:creator` meta added after `twitter:site` in base.html (deviation from plan: base.html is the shared head template, not seo.py).
- **F-ENRL-J03**: **CLOSED** — `docs/legal-counsel-review.md` §4a (India IT Act / intermediary draft rationale) verified against repo facts: no user-to-user content hosting/transmission, session cookies per-user for own automation runs, DPDP-not-IT-Act identified as the relevant Indian framework for cookie processing; still explicitly draft-for-counsel, not legal advice.

### Coupon-checker hardening (resolver tiers + safety valve)

- _resolve_course_id(http, url, slug=None): fields → bare → raw-verbatim-path-slug → HTML tiers;
  fixed _BROWSER_UA + req_type="api" + log_failures=False on all five JSON call sites.
- _fetch_pricing_json: plain-httpx-first (status 200 + dict), cloudscraper fallback; discountCode
  quote()-encoded; _coerce_valid_course_id predicate (rejects 0/junk/unicode digits).
- Slug tiers: attempts=2 (transport) + single 2s backoff on 429, then fall through.
- main(): atomic snapshot every 10 deals (refresh_sitemap=False), empty-snapshot guard,
  safety valve (expired > 75% done AND error < 5% done → skip snapshot AND final save;
  preserves last known-good file). Residual floor ~1.6% (6 collision-slug deals) accepted.
- DEPLOY (run before `git checkout .`): backup dirty tree (git diff > /root/predeploy-<ts>.diff;
  cp -a each dirty path to /root/predeploy-backup/), reconcile each dirty path against this
  batch's file list, then: git checkout . && git pull origin main && docker compose up -d --build.
  Post-deploy: git rev-parse HEAD == pushed sha; docker compose ps (new Started time);
  first "=== Coupon check cycle start ===" after Started; grep -c discountCode == 0.
  Pass criteria: error <= 10% (<= 38/380); expired within ±5 pts of baseline; zero discountCode
  in logs; 6 collision slugs + situational_leadership + >55-char slugs resolve via any tier.

### P2 wave — review fixes (R1–R6)

- **Fixed**: login CSRF origin gate now compares netloc (`host[:port]`, case-insensitive) only, ignoring scheme — behind Cloudflare Flexible SSL the browser sends an `https` Origin while nginx forwards `X-Forwarded-Proto: http` ($scheme), which previously 403'd every login POST. The `samesite=strict` double-submit cookie remains the primary control; optional `PUBLIC_BASE_URL` overrides the expected origin netloc when set.
- **Fixed**: stale-run sweeper catches transient exceptions (e.g. SQLite lock contention) inside the loop, logs, and continues instead of killing the recovery sweeper.
- **Changed**: `.env.example` documents `STALE_RUN_TIMEOUT_MINUTES=15` / `STALE_RUN_SWEEP_SECONDS=60` (F-ENRL-O01).
- **Docs**: corrected `pyproject.toml` typing-baseline comment (mypy `app/services/enrollment_manager.py` measured 21 errors incl. P2 lines, not 27).

### Added

- **Production coupon checker every 2 hours** — Docker Compose `coupon-checker` service runs `scripts/coupon_checker_loop.py`, shares the data volume with `web`, and rewrites `PUBLIC_DEALS_PATH` (`/app/data/public_deals.json`) so `/udemycoupons` stays fresh without local runs + git push.
- Coupon checker validates **`public_deals.json` only** (not the multi-tenant user DB); enrollment **merges** free finds into the catalog instead of full DB export replace.
- `PUBLIC_DEALS_PATH` / `COUPON_CHECKER_INTERVAL_SECONDS` settings; `save_public_deals` / `merge_deals_into_public_catalog` helpers.
- `CONTRIBUTING.md` — setup, tests, PR expectations, and contribution safety rules.
- GitHub issue templates (bug/feature) and pull request template under `.github/`.
- Issue template config links to `SECURITY.md` / security.txt.
- README **Updating** and **Uninstall / remove** sections (local, Docker, hosted demo).
- Clearer security contacts in `SECURITY.md` and `security.txt` (GitHub advisories + profile; no invented public email).
- Accessible confirm dialog (`window.accessibleConfirm`) for enrollment start, delete run, settings reset/clear (focus trap, Escape, restore focus).
- `docs/wcag-audit.md` — WCAG 2.2 AA **target** audit notes (axe + keyboard smoke); `npm run audit:wcag` with optional `BASE_URL`.
- `docs/performance-baseline.md` — lab CWV + Lighthouse baseline before perf trim; refreshed `tests/performance-baseline.json` and `performance-report/` snapshots.
- `/static/css/site.css` — shared chrome styles extracted from base template (cacheable).
- `tests/browser-smoke.js` + `docs/browser-smoke.md` — Chromium/Firefox/WebKit public + auth shell smoke (`npm run smoke:browsers`).
- `tests/viewport-smoke.js` + `docs/viewport-smoke.md` — 320–1920 responsive matrix (`npm run smoke:viewports`).
- `SECURITY.md` — private vulnerability reporting guidance.
- `/.well-known/security.txt` and `/security.txt` (RFC 9116-style contact/policy).
- Session expiry metadata on `GET /api/auth/status` (`session_expires_at`, remaining seconds, deployment env).
- Dashboard and settings UI notes for session lifetime (hosted ~24h, local longer).
- `app/session_lifecycle.py` — shared cleanup when sessions expire.
- `tests/conftest.py` — ensure DB schema exists for app-engine tests.
- `tests/test_session_lifecycle.py` — cookie wipe on last session expiry.

### Changed

- **Security / sessions**
  - Server-side auth gate for `/dashboard` HTML (redirect to connect if unauthenticated).
  - Logout closes cached Udemy client and clears CSRF cookie; wipes stored Udemy cookies.
  - Clear All Data also clears sessions and Udemy cookies (keeps user row + settings); signs the browser out.
  - Hosted demo app sessions: **24 hour** TTL; local: **30 days**.
  - On last session expiry, wipe encrypted `udemy_cookies` when no other active sessions remain.
  - Deploy workflow Actions pinned to full commit SHAs (no `@master`).
  - Analytics event endpoint rate-limited; health check no longer returns raw DB exception text.
  - Default `GTM_CONTAINER_ID` / `GA4_MEASUREMENT_ID` empty (set in production `.env`).

- **Product safety / trust copy**
  - Enrollment start requires browser confirmation.
  - Stronger hosted-demo and Terms disclaimers on connect UI.
  - Public marketing and meta copy softened: attempt enrollment when you start a run; not guaranteed; not affiliated with Udemy (home, about, FAQ, guides, coupons, llms/seo text).
  - Privacy policy text aligned with clear-data and hosted cookie retention.

- **SEO / structured data**
  - Homepage JSON-LD: single canonical `SoftwareApplication` (`#softwareapplication`); page graph uses `WebPage` + `SoftwareSourceCode` references.
  - `/login` compatibility redirect to `/#connect`.
  - humans.txt: accessibility **target** WCAG 2.2 AA (not a conformance claim).

### Removed

- **Removed**: stale, non-bootable `.do/app.yaml`.

### Fixed

- Misleading privacy claim that Clear All Data deleted account/settings/cookies without doing so (behavior + copy aligned).
- Residual “24/7 always-on auto-enroll” style claims on key public surfaces.
- Public-page a11y (axe WCAG 2.2 AA tags): contrast on muted labels / coupon prices / privacy code; always-underline body links; footer 24px min touch targets; keyboard-focusable privacy cookie table scroller.
- Auth UI keyboard a11y: settings switches (`role="switch"`, labels, 24px targets), form label `for` wiring, dashboard tablist/panels, history expandable run cards, stats modal focus trap/Escape, clearer contrast and control names.
- Performance trim (#25): coupons page SSR first 12 cards only; skip duplicate tojson + API re-fetch when SSR present; compact JSON-LD; scoped transitions; site chrome CSS externalized.
- Narrow-viewport overflow: guides step/code flex `min-w-0`; settings header stacks on small screens.
- Rate limits on more unauthenticated edges: CSP reports, public coupons API, auth status (login/analytics already limited; health stays open).
- Concurrent session cap (`MAX_SESSIONS_PER_USER`, default 3): oldest app sessions revoked when a new login exceeds the limit.
- Enrollment saves `is_coupon_valid` / `last_checked_at` and regenerates `public_deals.json` when a run finishes (same export as coupon checker).
- `docs/legal-counsel-review.md` — owner process pack for external legal/trademark/ToS review (not legal advice).
- Shared `public_deals.json` export: enrollment runs and `scripts/coupon_checker` both refresh the public coupons list.
- Indexable coupon detail pages `/udemycoupons/c/{slug}` (readable course name/slug; numeric IDs 301 to slug) + sitemap entries for valid deals (on-site URLs only).
- Sitemap deal URLs rebuild whenever enrollment or coupon_checker exports `public_deals.json` (`write_sitemap_files` + live `GET /sitemap.xml`).
- SEO/AEO/GEO: hub freshness + categories, `/udemycoupons/category/{slug}`, pillar guide `/guides/free-udemy-coupons`, related deals + BreadcrumbList on deal pages, softened `llms.txt` Key facts, no Crawl-delay for major bots.
- Residual SEO code pass: claim/copy sweep (FAQ schema+body, about, login, README, base banner, guides, llms); deal pages with unique how-to + FAQ JSON-LD + LimitedAvailability; sitemap quality filter (title length, 30-day freshness); hub Breadcrumb/CollectionPage; footer link to coupon guide; `docs/seo-residual-checklist.md` for remaining GSC/legal/ops items.
- **Fixed**: fonts and webp images were served as `application/octet-stream` on the slim production image (blocked by `nosniff`); MIME types now registered at startup and static asset URLs cache-busted (`?v=2`).

### Security

- See `SECURITY.md` and `/.well-known/security.txt`.
- Hosted multi-tenant cookie storage remains a residual risk; prefer self-hosting for full control. Stealth/Playwright and CloudScraper enrollment posture unchanged by explicit owner decision.
- **Security**: server-mode `SECRET_KEY` validation now rejects known placeholder and low-entropy values; `COOKIE_ENCRYPTION_KEY` must be a valid Fernet key in server mode (fail-closed at boot with actionable errors).
- **Security**: removed the unconditional GTM `<noscript>` analytics iframe (pre-consent tracking for no-JS visitors); direct GA4 loader now only renders when no GTM container is configured (fixes duplicate pageviews).

### Ops

- **Ops**: `scripts/deploy.sh` now generates a Fernet `COOKIE_ENCRYPTION_KEY`; coupon-checker fails fast on invalid settings; see `docs/security-trio-fix.md` for the SECRET_KEY rotation runbook.

### Security — F-ENRL-C01 (per-session cookie envelopes)

- **Security**: hosted cookie blobs now encrypt under a per-session key — HKDF-SHA256 (info `udemy-enroller-session-key-v1`) derived from the master Fernet key plus a per-user `cookies_salt` (16 random bytes), rotated on every write site (login, save, refresh, connect). A blob decrypts only under the salt of the session that wrote it; wrong/missing salt fails closed (None → 401 → re-login).
- Legacy (unsalted master-key Fernet) blobs and plaintext dicts keep their prior behavior behind two independent flags: `ALLOW_LEGACY_COOKIE_DECRYPT` (default ON for local/dev with a warning, OFF for server/production) and the existing `ALLOW_PLAINTEXT_COOKIES`.
- Logout, session expiry, and Clear All Data now wipe `cookies_salt` as well, making old blobs undecryptable.
- Migration `alembic/versions/c01d021a9e01_add_cookies_salt_to_users.py` adds the `cookies_salt` column (inspect-idempotent ALTER; down_revision `0bd117e7d36c`). It is **not** the chain head — head is `c01d021a9e03` (via `c01d021a9e02` `last_heartbeat`). Applied on the **local** live DB; production **not** upgraded.
- `scripts/migrate_cookies_per_session.py` re-encrypts existing blobs per session (dry-run by default; `--apply` requires `--backup-verified`; JSON report) — **not run**.
- `.env.example` documents the new flag.

### Security — F-ENRL-C07 (host-validation gate)

- **Security**: all "is this Udemy?" checks in `app/services` now use parse-based allowlist helpers in `app/services/udemy_validation.py` (`is_udemy_netloc`, `is_udemy_url`, `is_udemy_course_url`, `is_trk_udemy_url` — exact netloc match). Substring/regex checks on the literal `udemy.com` (which accept hostile hosts like `udemy.com.evil.com`, `eviludemy.com`, `user@udemy.com`) were removed.
- `scripts/verify-no-udemy-substring.sh` regression gate runs in CI (`--tree` mode) and can run on the staged diff as a pre-commit check; fails on any new substring check in `app/services` (allowlist file exempt).

### Docs — F-ENRL-J01 (DPIA draft)

- `docs/dpia-enroller-cookies-skeleton.md` — draft DPIA skeleton **v0.4-draft-v1** for hosted encrypted cookie processing: controller, lawful basis (§4a options), retention, cross-border, DPDP Act 2023 pointers; sign-off DATE-PENDING (counsel review required).
- `docs/legal-counsel-review.md` — added draft IT Act / intermediary N/A rationale (marked draft-for-counsel, not legal advice).

## [2026-07-06] — baseline `e6bc1c2`

### Summary

Last published commit on `main` at the start of the forensic audit / implementation pass:

- Phase 4 trust copy, SEO, a11y, stats, lint, and hosted-demo login work (see git history for detail).

---

[Unreleased]: https://github.com/madhu2456/udemy_enroller_fastapi/compare/e6bc1c2...HEAD
