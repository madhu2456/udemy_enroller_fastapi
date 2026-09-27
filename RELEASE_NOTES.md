# Udemy Course Enroller — v1.0.0 General Availability (GA)

> **Release Version**: `v1.0.0`  
> **Release Date**: 2026-09-27  
> **Repository**: [madhu2456/udemy_enroller_fastapi](https://github.com/madhu2456/udemy_enroller_fastapi)  
> **Live Demo**: [udemyenroller.madhudadi.in](https://udemyenroller.madhudadi.in)  
> **License**: MIT  

---

## Downloads

<table>
<thead>
  <tr>
    <th align="center">GUI (Desktop Application)</th>
    <th align="center">CLI (Command-Line Tool)</th>
  </tr>
</thead>
<tbody>
  <tr align="center">
    <td>
      <a href="https://github.com/madhu2456/udemy_enroller_fastapi/releases/latest/download/Gui.exe">
        <img alt="Download GUI Windows exe" src="https://img.shields.io/static/v1?message=Download%20Gui.exe&logo=windows&labelColor=5c5c5c&color=1182c3&label=%20&style=for-the-badge">
      </a>
      <br/>
      <sub><b>Gui.exe</b> — Standalone Windows Desktop GUI</sub>
    </td>
    <td>
      <a href="https://github.com/madhu2456/udemy_enroller_fastapi/releases/latest/download/cli.exe">
        <img alt="Download CLI Windows exe" src="https://img.shields.io/static/v1?message=Download%20cli.exe&logo=windows&labelColor=5c5c5c&color=1182c3&label=%20&style=for-the-badge">
      </a>
      <br/>
      <sub><b>cli.exe</b> — Standalone Windows Terminal CLI</sub>
    </td>
  </tr>
  <tr align="center">
    <td colspan="2">
      <a href="https://github.com/madhu2456/udemy_enroller_fastapi/releases/latest">
        <img alt="All Releases & Linux/macOS Binaries" src="https://img.shields.io/badge/All%20Releases-Linux%20%7C%20macOS%20%7C%20Source-blueviolet?style=for-the-badge">
      </a>
    </td>
  </tr>
</tbody>
</table>

> **Quick Run:** No Python installation required. Simply download `Gui.exe` and double-click to launch the native interface, or run `cli.exe --help` in Command Prompt / PowerShell.<br/>
> *(If Windows SmartScreen appears: click "More info" → "Run anyway". All binaries are open-source and built transparently via GitHub Actions).*

---

## 1. Executive Summary & Overview

We are proud to announce the **v1.0.0 General Availability (GA)** release of **Udemy Course Enroller**! This release marks the official transition from development to a hardened, production-ready, self-hosted automation platform.

Udemy Course Enroller discovers 100% off Udemy coupons across 17 aggregator sources and automates enrollment when you initiate a run. Designed with a security-first architecture, it operates with **zero master passwords handled**, utilizing session-based browser cookies and platform keychain decryption.

---

## 2. 17-Aggregator Scraper Fleet Matrix

The high-throughput scraper fleet harvests live 100% off coupon deals across 17 distinct aggregators with domain-partitioned pacing, exponential jitter, anti-bot emulation, and React Server Components (RSC) Flight stream parsing:

| # | Aggregator | Identifier | Extraction Engine & Parsing Strategy |
|:---:|:---|:---:|:---|
| 1 | **Courson** | `cs` | Paginated API (`/load-more-coupons`) & dynamic JSON state parsing |
| 2 | **CouponScorpion** | `csc` | REST API (`/wp-json/wp/v2/posts`) + 0-hop regex resolution |
| 3 | **FreeCourseSites** | `fcs` | Multi-category HTML crawling & single-hop `/out/` unwrap |
| 4 | **E-next** | `en` | Fast XML/HTML pagination & 0-hop redirect unmasking |
| 5 | **Interview Gig** | `ig` | Next.js API crawling & course metadata extraction |
| 6 | **UdemyXpert** | `ux` | Multi-tier catalog crawler & direct coupon link parsing |
| 7 | **Coursesity** | `cu` | Angular 18 SSR TransferState (`app-root-state`) extraction |
| 8 | **Course Folder** | `cf` | Category-level crawling & discrete chunked batching |
| 9 | **Couponami** | `cn` | Fast HTML offer extraction & anti-bot emulation |
| 10 | **Korshub** | `kh` | Next.js Flight RSC stream (`self.__next_f`) extraction |
| 11 | **UdemyFreebies** | `uf` | Paginated listing crawler & single-hop `/out/{slug}` unwrap |
| 12 | **iDownloadCoupon** | `idc` | WooCommerce Store REST API (`/wp-json/wc/store/v1/products`) |
| 13 | **Real Discount** | `rd` | Direct CDN REST API (`cdn.real.discount/api/courses`) 0-hop links |
| 14 | **OnlineCourses.ooo** | `oc` | RSS XML feed ingestion + ReHub fallback (disabled by default) |
| 15 | **FreebiesGlobal** | `fg` | Tag archive harvesting (`/tag/udemy-100-off/`) & direct card links |
| 16 | **GeeksGod** | `gg` | Paginated catalog harvesting & tracking parameter sanitization |
| 17 | **TutorialBar** | `tb` | Next.js React Server Components (RSC) Flight 0-hop extraction |

---

## 3. Background Enrollment Engine & Two-Tier Circuit Breaker

The core enrollment engine is engineered to prevent Cloudflare 403 checkout storms and eliminate redundant checkouts:

- **Two-Tier Checkout Circuit Breaker**:
  - **Soft Tier (1st 403)**: Automatically performs an in-flight CSRF token renewal and retries the checkout.
  - **Hard Tier ($\ge 2$ consecutive 403s)**: Trips global breaker with exponential backoff cooldown (`min(45 * (2 ** (trip - 1)), 180)` seconds).
  - **Double-Checked Locking**: Protected by `asyncio.Semaphore(1)` to ensure queued workers never execute during an active cooldown.
  - **Monotonic Clock**: Uses `time.monotonic()` to guarantee cooldowns are completely immune to system NTP time adjustments.
- **Two-Phase Complete Library Synchronization**:
  - **Phase 1 (Active Courses)**: Fast sync (`?is_archived=false`) with 10-consecutive early-stop (< 3s startup time).
  - **Phase 2 (Archived Courses)**: Background sync (`?is_archived=true`) with 5-page checkpointing (`archived_sync_cursor_page`) up to 500 pages, permanently bridging library count discrepancies.
  - **Persistent Cache**: Once synchronized, cached slugs prevent unnecessary checkout calls on already-owned courses.

---

## 4. Multi-Platform Interfaces

1. **Native Desktop GUI ([CustomTkinter](https://customtkinter.tomschimansky.com))**:
   - Packaged as standalone `Gui.exe` (Windows) and `Gui` (Linux/macOS).
   - Features Dark and Light themes with dynamic switching.
   - Dual progress bars (scraping and enrollment) with real-time speed calculation.
   - Memory-safe 1,000-line FIFO log console with automatic log sink teardown.
2. **Unified Headless CLI ([Typer](https://typer.tiangolo.com) + [Rich](https://rich.readthedocs.io))**:
   - Packaged as standalone `cli.exe` (Windows) and `cli` (Linux/macOS).
   - 8 subcommands: `login`, `logout`, `enroll`, `scrape`, `check`, `stats`, `server`, and `--version`.
   - Dual-channel output: pure JSON on `stdout` and human-friendly Rich formatting / logging on `stderr`.
   - Supports `--dry-run` simulation for CI pipelines and automation testing.
3. **Web Interface & REST API ([FastAPI](https://fastapi.tiangolo.com))**:
   - Server-side rendered (SSR) Jinja2 templates with Tailwind CSS styling.
   - Dedicated above-the-fold `/login` page with secure cookie connection guidance.
   - Real-time Server-Sent Events (SSE) log streaming and dashboard savings counters.
   - Interactive OpenAPI/Swagger documentation at `/docs`.

---

## 5. Defense-in-Depth Security Architecture

- **Per-Session Fernet Cookie Encryption (F-ENRL-C01)**:
  - Cookies encrypted under HKDF-SHA256 derived keys (`info=b"udemy-enroller-session-key-v1"`) with 16 random salt bytes (`cookies_salt`).
  - Wrong or missing salt fails closed (HTTP 401).
- **Exact URL Netloc Validation (F-ENRL-C07)**:
  - All Udemy URL checks strictly enforced via parse-based allowlist helpers (`is_udemy_netloc`, `is_udemy_url`, `is_udemy_course_url`), completely removing insecure substring matches.
- **SSRF Fencing & DNS Caching**:
  - Outbound HTTP requests guarded by IP validation blocking RFC 1918, RFC 3927 (link-local/cloud metadata), loopback, and multicast addresses.
- **Double-Submit CSRF Protection (F-ENRL-C03)**:
  - Enforces `__Host-csrf_token` (production) and `csrf_token` (local) double-submit verification on state-changing endpoints.
- **Content Security Policy (CSP)**:
  - Cryptographic per-request nonces (`csp_nonce`) on all inline script and style elements.

---

## 6. Technical SEO, AEO & Accessibility Compliance

- **Schema.org JSON-LD `@graph`**: Rich structured data for `SoftwareApplication`, `HowTo` setup guides, and `FAQPage`.
- **IndexNow Protocol**: Automated real-time indexation notifications to Bing and Yandex on deployment.
- **WCAG 2.2 AA Accessibility**:
  - Color contrast ratios $\ge 4.81:1$ on all rendered text elements.
  - Interactive touch targets satisfy 44px minimum bounding box requirements.
  - Screen-reader accessible ARIA live regions (`aria-live="polite"`) on alerts and form inputs.

---

## 7. Packaging & Standalone Executables

- Standalone executable compilation powered by PyInstaller with dependency pre-flight protection (`build_exe.py`).
- Automated multi-platform GitHub Actions build matrix (`.github/workflows/build-executables.yml`):
  - **Windows**: `Gui.exe` and `cli.exe`
  - **Linux**: `Gui-linux` and `cli-linux`
  - **macOS**: `Gui-macos` and `cli-macos`
- Zero-configuration execution without requiring Python or pip on client workstations.

---

## 8. Verifying & Upgrading to v1.0.0

```bash
# Clone or pull latest release
git clone https://github.com/madhu2456/udemy_enroller_fastapi.git
cd udemy_enroller_fastapi

# Verify CLI version
./venv/bin/python -m app.cli.main --version
# Output: Udemy Enroller v1.0.0

# Run standalone desktop app
python gui.py
```
