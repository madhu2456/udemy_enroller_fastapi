# Udemy Course Enroller - Automated Free Udemy Course Enrollment

* **Built by**: Madhu Dadi
* **Canonical profile**: https://madhudadi.in/profile/
* **Case study**: https://madhudadi.in/case-studies/udemy-enroller-fastapi/
* **Service relevance**: Python/FastAPI Automation & Data Engineering

---

> **⚠️ Disclaimer:** This project is **NOT affiliated, endorsed, or connected with Udemy or any of its affiliates.** "Udemy" is a registered trademark of Udemy, Inc. This is an independent, open-source tool built for educational purposes. Users are solely responsible for ensuring their use complies with [Udemy's Terms of Use](https://www.udemy.com/terms/).
>
> A free, open-source FastAPI application that monitors coupon sources and can **attempt** enrollment in 100% discounted Udemy courses when **you start a run**. Success is not guaranteed. Built by [Madhu Dadi](https://madhudadi.in).

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Live-Demo-blue)](https://udemyenroller.madhudadi.in)

**Live Demo:** [https://udemyenroller.madhudadi.in](https://udemyenroller.madhudadi.in)  
**Case Study:** [https://madhudadi.in/case-studies/udemy-enroller-fastapi/](https://madhudadi.in/case-studies/udemy-enroller-fastapi/)  
**Developer Portfolio:** [https://madhudadi.in](https://madhudadi.in) | **Blog:** [https://madhudadi.in/blog](https://madhudadi.in/blog)

---

## ⚠️ Disclaimer

> **This project is NOT affiliated with, endorsed by, or connected to Udemy or its parent company.**  
> "Udemy" is a registered trademark of Udemy, Inc. This is an independent, open-source tool created for educational purposes.  
> Users are solely responsible for ensuring their use complies with [Udemy's Terms of Use](https://www.udemy.com/terms/).

## ⚠️ Platform Risk Acknowledgment

This tool uses **session-based Udemy enrollment endpoints**, not an official Udemy API.
Automated access may conflict with Udemy's Terms of Use. The maintainers have reviewed
this risk and determined it is acceptable for this open-source project. Users are solely
responsible for ensuring their use complies with applicable terms and laws.

---

## What is Udemy Course Enroller?

**Udemy Course Enroller** is an asynchronous application and ecosystem built with **Python**, **FastAPI**, **CustomTkinter**, and **Typer/Rich** that helps you discover free (often 100% off) Udemy course coupons and **attempt** enrollment when you start a run. While a run is active, it monitors **17 aggregator scrapers** — Courson, CouponScorpion, FreeCourseSites, E-next, Interview Gig, UdemyXpert, Coursesity, Course Folder, Couponami, Korshub, UdemyFreebies, iDownloadCoupon, Real Discount, OnlineCourses.ooo, FreebiesGlobal, GeeksGod, and TutorialBar — applies your filters, and uses session-based Udemy enrollment endpoints. Enrollment success and coupon validity are **not guaranteed**.

You can run Udemy Enroller via the **Web Interface** (`python run.py`), **Modern Desktop GUI** (`python gui.py`), or **Unified Rich CLI** (`python cli.py`). You can also browse public free-coupon listings without automation. Prefer self-hosting if you want full control over where session cookies are stored.

---

## Why This Exists

Premium online education on platforms like Udemy can be expensive. However, instructors frequently share **100% off coupons** on aggregator sites to build reviews and reach new students. The problem? These coupons expire within hours - sometimes minutes.

This tool helps with that by:
- **Monitoring** 17 configured coupon sources when you start an enrollment run
- **Filtering** courses by category, language, rating, and instructor
- **Attempting enrollment** via Udemy's session-based enrollment endpoints (not guaranteed)
- **Tracking** recorded enrollments and estimated savings on the dashboard

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Modern Desktop GUI** | Native CustomTkinter app with Dark/Light themes, dual progress bars, 17-scraper grid, and FIFO logs (`python gui.py`) |
| **Unified Rich CLI** | Headless CLI powered by Typer & Rich with 5 subcommands (`enroll`, `scrape`, `check`, `stats`, `server`) and `--dry-run` |
| **1-Click Cookie Extraction** | Universal safe cookie importer for Chrome, Edge, Firefox, Brave, Opera, and Chromium with zero-lock tempdir queries |
| **17-Scraper Fleet** | High-capacity fleet extracting up to 500 coupons per source via RSC Flight streaming, Angular SSR, and REST APIs |
| **Run-Based Automation** | Set filters, start a run; the engine monitors sources while the run is active |
| **Smart Filtering** | Exclude categories, languages, low-rated courses, or specific instructors |
| **Cookie-Based Auth** | Secure login using Udemy session cookies - no passwords stored |
| **Bulk Enrollment** | Intelligently batches API requests to respect rate limits |
| **Real-Time Dashboard** | Live progress tracking, savings analytics, and enrollment history |
| **Session Persistence** | Encrypted cookie storage with automatic session reconstruction |
| **Self-Hostable** | Docker + docker-compose support for private deployments |
| **SEO & AEO Optimized** | Built-in sitemap, structured data, LLMs.txt, and AI-profile.json |

---

## Technical Architecture

This application is built on a modern, fully asynchronous Python stack:

- **Backend:** Python 3.11+ + [FastAPI](https://fastapi.tiangolo.com) (async)
- **Database:** SQLite + [SQLAlchemy](https://www.sqlalchemy.org) ORM + Alembic migrations
- **Automation:** [CloudScraper](https://github.com/VeNoMouS/cloudscraper) (primary HTTP client) + [Playwright](https://playwright.dev/python/) (fallback browser client for some coupon aggregator sites), with rate-limited requests and no CAPTCHA solving
- **Frontend:** HTML5 + [Tailwind CSS](https://tailwindcss.com) + vanilla JavaScript
- **Deployment:** Docker + docker-compose ready

The frontend is intentionally lightweight to ensure sub-second load times. Server-Sent Events (SSE) power the live log stream and enrollment progress updates.

**PWA / service worker:** A Web App Manifest is served at `/manifest.webmanifest` (install metadata and icons only). **No service worker is shipped** — offline caching and background sync are intentionally out of scope to keep the surface area small and avoid stale-asset risk on a frequently updated coupon UI.

---

## Quick Start

### Prerequisites
- Python 3.11+ (or Docker)
- A Udemy account

### Option 1: Local Setup

```bash
# Clone the repository
git clone https://github.com/madhu2456/udemy_enroller_fastapi.git
cd udemy_enroller_fastapi

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment (optional)
cp .env.example .env

# Inspect + backup the live SQLite file, then pin the upgrade (never bare alembic upgrade head).
# See docs/ops/backup-restore.md
LIVE_ABS="$PWD/udemy_enroller.db"   # or the inspected live path
touch "$LIVE_ABS"
python scripts/inspect_sqlite_schema.py "$LIVE_ABS"
DB_PATH=$LIVE_ABS ./scripts/backup_sqlite.sh backup
python scripts/alembic_upgrade_pinned.py "$LIVE_ABS" head

# Start the server
python run.py
```

The application will be available at `http://localhost:8000`.

### Option 2: Docker

By default, containerized deployments run in `DEPLOYMENT_ENV=server` mode to enforce strict production security. **The container will fail to start if you do not configure a strong, unique `SECRET_KEY`** — placeholder/`change-me` values and a missing or invalid `COOKIE_ENCRYPTION_KEY` (must be a valid Fernet key) are rejected at boot with an actionable error. `scripts/deploy.sh` now generates both keys automatically (requires `python3` + `python3-cryptography` on the host). See [docs/security-trio-fix.md](docs/security-trio-fix.md) for the key-rotation runbook.

1. Clone and navigate to the directory:
   ```bash
   git clone https://github.com/madhu2456/udemy_enroller_fastapi.git
   cd udemy_enroller_fastapi
   ```

2. Create a `.env` with strong secrets (required in `DEPLOYMENT_ENV=server`):
   ```bash
   openssl rand -hex 32   # SECRET_KEY
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # COOKIE_ENCRYPTION_KEY
   ```

   ```env
   SECRET_KEY=your_generated_strong_hex_key_here
   COOKIE_ENCRYPTION_KEY=your_fernet_key_here
   DEPLOYMENT_ENV=server
   ```

   See `.env.example` for optional analytics and other settings.

3. Launch the container:
   ```bash
   docker compose up -d --build
   ```

---

## How to Use

1. **Log into Udemy** in your browser (udemy.com)
2. **Extract cookies** via Developer Tools (F12 → Application → Cookies):
   - `access_token`
   - `client_id`
   - `csrftoken`
3. **Paste cookies** into the login form at the app's homepage
4. **Configure filters** in Settings (categories, languages, ratings, exclusions)
5. **Click "Start Enrollment"** on the Dashboard (confirm when prompted)
6. **Watch progress** as the run attempts enrollments and records results (success is not guaranteed)

For detailed setup instructions, visit the [Guides](https://udemyenroller.madhudadi.in/guides) page or read the [case study](https://madhudadi.in/case-studies/udemy-enroller-fastapi/).

---

## Modern Desktop GUI

Udemy Enroller includes a native desktop application powered by **CustomTkinter** that provides a modern, interactive dashboard with real-time feedback.

```bash
# Launch the Modern Desktop GUI
python gui.py
```

> [!NOTE]
> On Linux, ensure an active graphical display is available (`DISPLAY` or `WAYLAND_DISPLAY`) and Python `tkinter` is installed (e.g. `sudo apt install python3-tk`). In headless or SSH environments, use the [Unified Rich CLI](#unified-rich-cli).

### GUI Features & Architecture
* **Dark / Light Native Themes**: Seamlessly switch between dark and light themes with system auto-detection and persistent preferences.
* **Dual Concurrent Progress Bars**: Real-time visual tracking of batch-level scraper fleet progress alongside individual enrollment checkout loops.
* **17-Scraper Multi-Select Grid**: Interactive checkbox grid with quick batch toggles (*"Select All"*, *"Deselect All"*, *"Reset Defaults"*) to enable, disable, or isolate specific coupon sources.
* **1,000-Line Circular FIFO Log Console**: Embedded log viewer backed by a 1,000-line `collections.deque` buffer with auto-scroll lock, log-level color tagging, and dynamic **Pause / Resume** execution controls.
* **Thread-Safe `AsyncioBridge`**: Decouples CustomTkinter's GUI event loop from asynchronous backend services (`UdemyClient`, `ScraperService`, `browser_cookies`) via bidirectional thread queues (`command_queue` and `event_queue`).
* **1-Click Cookie Auto-Extraction**: Automatically extracts credentials from your default browser without needing developer tools.

---

## Unified Rich CLI

The unified CLI (`cli.py`) is powered by **Typer** and **Rich**, delivering beautiful terminal UI, live progress indicators, and complete headless automation.

```bash
# View general help and available subcommands
python cli.py --help
```

### 1. `login` — Authenticate & Persist Session
Extracts session cookies from installed browsers (or takes manual tokens), authenticates against the Udemy API, and saves the credentials to encrypted local storage for long-term CLI & GUI reuse.

```bash
# 1-Click extraction from default browser
python cli.py login

# Extract from specific browser
python cli.py login --browser chrome  # chrome, edge, firefox, brave, opera

# Provide tokens directly
python cli.py login --token YOUR_ACCESS_TOKEN --client-id YOUR_CLIENT_ID --csrf YOUR_CSRF_TOKEN
```

### 2. `logout` — Clear Saved Session
Securely deletes all saved persistent credentials and tokens from local encrypted storage.

```bash
python cli.py logout
```

### 3. `enroll` — Automated Scraping & Bulk Enrollment
Scrapes active coupons from all enabled sources, applies your filters, and automatically enrolls into matching courses using your saved session credentials.

```bash
# Basic run with saved session or auto-detected browser cookies
python cli.py enroll

# Simulation mode (scrapes and checks filters without enrolling)
python cli.py enroll --dry-run

# Specify browser or provide manual access token
python cli.py enroll --browser chrome
python cli.py enroll --token YOUR_UDEMY_ACCESS_TOKEN

# Apply custom filters and export results to JSON
python cli.py enroll \
  --categories "Development,IT & Software" \
  --languages "English,Spanish" \
  --min-rating 4.2 \
  --limit 30 \
  --output results.json
```

### 4. `scrape` — Standalone Coupon Harvester
Scrapes free Udemy courses across aggregator sites without submitting enrollment requests.

```bash
# Scrape and print as a formatted terminal table
python cli.py scrape

# Scrape specific sites and export to JSON or CSV
python cli.py scrape --sites "Courson,CouponScorpion" --format json --output scraped_courses.json
python cli.py scrape --sites "FreeCourseSites,TutorialBar" --format csv --output scraped_courses.csv --limit 100
```

### 5. `check` — Session Health & Coupon URL Verification
Verifies authentication credentials or probes a specific Udemy course coupon link.

```bash
# Check current session health using saved credentials or auto-extracted cookies
python cli.py check

# Validate a specific access token
python cli.py check --token YOUR_ACCESS_TOKEN

# Probe a single course coupon URL
python cli.py check --url "https://www.udemy.com/course/example-course/?couponCode=FREE100"
```

### 6. `stats` — Account Metrics & Historical Savings
Displays connected account profile, active session status, lifetime enrollment totals, and estimated money saved.

```bash
# View summary in terminal
python cli.py stats

# Export lifetime analytics to JSON
python cli.py stats --output lifetime_stats.json --limit 50
```

### 7. `server` — FastAPI Web Server Launcher
Convenient command to launch the FastAPI web application with Uvicorn.

```bash
# Launch server on default port 8000
python cli.py server

# Custom host, port, and auto-reload for development
python cli.py server --host 0.0.0.0 --port 8080 --reload
```

---

## Standalone Executables (`Gui.exe` & `cli.exe`)

For users who prefer running the applications without setting up a Python environment, standalone compiled binaries (`Gui.exe` and `cli.exe`) are available.

### Download Pre-Compiled Binaries
Pre-compiled executable packages for Windows, Linux, and macOS are automatically built on every release via GitHub Actions:
- **Windows**: `Gui.exe` (Windowed desktop app) and `cli.exe` (Console terminal app)
- **Linux**: `Gui` and `cli`
- **macOS**: `Gui` and `cli`

### Compiling Standalone Executables Locally
You can build standalone binaries directly on your machine using the cross-platform compiler:

```bash
# Build both Desktop GUI (Gui.exe / Gui) and Rich CLI (cli.exe / cli):
python build_exe.py --all

# Build only the Desktop GUI:
python build_exe.py --gui

# Build only the Unified CLI:
python build_exe.py --cli
```

The compiled binaries will be output into the `dist/` directory.

### CLI Ergonomics & CI Support
* **Interactive Wizard**: Automatically prompts for missing credentials or guided configuration when run interactively.
* **CI & Pipe Detection**: Built-in `is_tty()` detection automatically disables animations, progress bars, and spinners when output is redirected to files, pipes, or CI/CD automated runners.

---

## 1-Click Browser Cookie Import & Decryption

The universal cookie extraction service (`app/services/browser_cookies.py`) extracts active Udemy credentials (`access_token`, `client_id`, `csrftoken`) directly from your local browser without requiring manual Developer Tools copying.

### Supported Browsers
* **Google Chrome**
* **Microsoft Edge**
* **Mozilla Firefox**
* **Brave Browser**
* **Opera & Opera GX**
* **Chromium**

### How It Works
1. **Zero-Lock Immutable SQLite Extraction**: Copies SQLite cookie databases to an isolated temporary directory and opens them with SQLite URI mode `file:...uri=true&mode=ro&immutable=1`, ensuring your active browser is never locked or disrupted.
2. **Cross-Platform Decryption**:
   * **Linux**: Decrypts Chromium `v10` cookies using PBKDF2 HMAC SHA-1 key derivation (`saltysalt`, 24 iterations) with GNOME Keyring / SecretService / `peanuts` master key retrieval.
   * **Windows**: Extracts encrypted master keys from `Local State` via Windows DPAPI (`CryptUnprotectData`) and decrypts cookie payloads with AES-256-GCM.
   * **macOS**: Resolves master encryption keys via macOS Keychain and decrypts cookies using AES-128-CBC.
   * **Firefox**: Directly reads plain-text cookie records from `moz_cookies`.

### Troubleshooting Cookie Extraction
* **Active Browser Session**: Make sure you have logged into [udemy.com](https://www.udemy.com) in the browser at least once so session cookies are written to disk.
* **Windows Chrome 127+ App-Bound Encryption**: Newer Chrome versions (v127+) on Windows enforce elevated service-bound encryption (`v20` format). If detected, the tool provides clear guidance to:
  1. Use **Mozilla Firefox** or **Microsoft Edge** for seamless 1-click import (uses standard DPAPI).
  2. Or provide the `access_token` manually via CLI `--token` flag or GUI login screen.

---

## Full 17-Scraper Fleet Capabilities

Udemy Enroller coordinates a fleet of **17 high-throughput aggregator scrapers**, extracting up to 500 valid coupons per source with cutting-edge parsing strategies:

| # | Scraper Name | Identifier | Extraction Engine & Strategies |
|---|--------------|------------|--------------------------------|
| 1 | **Courson** | `cs` / `courson` | Paginated API (`/load-more-coupons`), dynamic JSON state parsing |
| 2 | **CouponScorpion** | `csc` / `couponscorpion` | REST API (`/wp-json/wp/v2/posts`) + 0-hop fast regex hop resolution |
| 3 | **FreeCourseSites** | `fcs` / `freecoursesites` | Multi-category HTML crawling, single-attempt `/out/` unwrap |
| 4 | **E-next** | `en` / `enext` | Fast XML/HTML pagination, 0-hop redirect unmasking |
| 5 | **Interview Gig** | `ig` / `interviewgig` | Next.js API crawling, course metadata extraction |
| 6 | **UdemyXpert** | `ux` / `udemyxpert` | Multi-tier catalog crawler, direct coupon link parsing |
| 7 | **Coursesity** | `cu` / `coursesity` | Angular 18 SSR TransferState (`<script id="app-root-state">`) extraction |
| 8 | **Course Folder** | `cf` / `coursefolder` | Category-level crawling, discrete chunked batching |
| 9 | **Couponami** | `cn` / `couponami` | Fast HTML offer extraction, anti-bot header emulation |
| 10 | **Korshub** | `kh` / `korshub` | Next.js Flight RSC stream extraction (`self.__next_f`), JSON-LD regex matching |
| 11 | **UdemyFreebies** | `uf` / `udemyfreebies` | Paginated listing crawler, single-hop `/out/{slug}` unwrap, reserved slug filtering |
| 12 | **iDownloadCoupon** | `idc` / `idownloadcoupon` | WooCommerce Store REST API (`/wp-json/wc/store/v1/products`) with HTML fallback |
| 13 | **Real Discount** | `rd` / `realdiscount` | Direct CDN REST API (`https://cdn.real.discount/api/courses`), 0-hop coupon links |
| 14 | **OnlineCourses.ooo** | `oc` / `onlinecourses` | RSS XML feed ingestion + paginated crawling, ReHub CSS selector fallbacks |
| 15 | **FreebiesGlobal** | `fg` / `freebiesglobal` | Tag archive harvesting (`/tag/udemy-100-off/`), 0-hop card link parsing |
| 16 | **GeeksGod** | `gg` / `geeksgod` | Paginated catalog harvesting, tracking parameter sanitization (`rand=4`, `ref` stripped) |
| 17 | **TutorialBar** | `tb` / `tutorialbar` | Next.js React Server Components (RSC) Flight stream parsing, 0-hop coupon extraction |

### Fleet Highlights
* **Fleet Capacity Scaling**: Standardized to harvest up to **500 latest active courses per scraper** across all 17 sources.
* **0-Hop Resolution**: Direct coupon extraction via React Server Components (RSC) Flight chunks, Angular SSR TransferState, and JSON REST APIs, minimizing intermediary network hops.
* **Anti-Zombie Chunked Batching**: All scrapers execute concurrent detail resolution in discrete chunks (`DETAIL_BATCH_SIZE = 10`) with immediate loop termination, eliminating background task leaks.

---

## Updating

### Local (git + venv)

```bash
cd udemy_enroller_fastapi
git pull origin main
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
# Pin Alembic to the inspected live file after backup (docs/ops/backup-restore.md)
LIVE_ABS="$PWD/udemy_enroller.db"   # or the inspected live path
python scripts/alembic_upgrade_pinned.py "$LIVE_ABS" head
# Restart the app (stop python run.py / uvicorn, then start again)
python run.py
```

If you changed Tailwind sources:

```bash
npm ci
npm run build:css
```

### Docker

```bash
cd udemy_enroller_fastapi
git pull origin main
docker compose up -d --build
```

Production pushes to `main` can also deploy via **GitHub Actions** (`.github/workflows/ci.yml`), if that workflow is configured for your server.

After updates, re-check `.env.example` for any new variables (for example `COOKIE_ENCRYPTION_KEY` and analytics IDs in server mode).

---

## Uninstall / remove

### Local

1. Stop the app (Ctrl+C if running in a terminal, or stop the process/service).
2. Optional: export or back up data first (see [Backup & Recovery](#backup--recovery)).
3. Remove the project directory (this deletes the app, venv, and local DB if they live there):
   ```bash
   # From the parent directory — adjust the folder name if different
   rm -rf udemy_enroller_fastapi
   ```
4. If you installed the Chrome extension unpacked: Chrome → Extensions → remove **Udemy Enroller - Cookie Extractor**.
5. Browser cookies for the app origin are separate from Udemy; clear site data for your enroller URL if desired.

### Docker

```bash
cd udemy_enroller_fastapi
docker compose down
# Optional: remove built images
docker compose down --rmi local
# Optional: remove named volumes (DESTROYS container data)
docker compose down -v
```

Then delete the project directory if you no longer need the files.

### Hosted demo

There is nothing to uninstall for the public demo. Use **Logout** and/or **Clear All Data** in Settings to remove your session cookies and enrollment history on that instance (see [Privacy](https://udemyenroller.madhudadi.in/privacy)).

---

## Validating Expired Coupons

The application checks coupon listing validity for the public `/udemycoupons` page (`public_deals.json`). Prefer mocks/fixtures in development; be mindful of third-party rate limits and terms.

**How the public catalog is maintained:**

1. **Standalone checker (source of truth for validity)** — reads `public_deals.json`, re-checks each coupon on Udemy, drops expired deals, rewrites the file + sitemap. **Does not use the user/enrollment database.**
2. **Enrollment run** — may **merge** newly found free coupons from that run into the catalog (upsert); it does **not** replace the whole file from the multi-tenant DB.

`GET /sitemap.xml` always rebuilds from the current `public_deals.json` (valid slugs only). A disk snapshot is also written as `sitemap.generated.xml` / `sitemap.meta.json` after each export.

### Running Locally
From the project root:
```bash
./scripts/coupon_checker.sh
```

### Production: automatic every 2 hours (recommended)

`docker-compose.yml` includes a **`coupon-checker`** service that:

- Shares the same `app-data` volume as `web` (`public_deals.json` on the volume)
- Runs `scripts/coupon_checker_loop.py` on an interval (default **7200s = 2 hours**)
- Re-validates the **catalog file** (not user DB rows) and writes to `PUBLIC_DEALS_PATH=/app/data/public_deals.json` so updates **survive** rebuilds

After deploy / restart:

```bash
cd /opt/udemy-enroller   # or your app dir
docker compose up -d --build
docker compose ps        # web + coupon-checker should be up
docker compose logs -f coupon-checker
```

Optional env (in `.env` on the server):

```env
COUPON_CHECKER_INTERVAL_SECONDS=7200
COUPON_CHECKER_RUN_ON_START=true
PUBLIC_DEALS_PATH=/app/data/public_deals.json
```

### One-shot on the server

```bash
# Immediate re-check without waiting for the next loop tick
docker compose exec -T coupon-checker python -u scripts/coupon_checker.py
# or:
docker compose exec -T web python -u scripts/coupon_checker.py
```

You no longer need to run the checker locally and git-push `public_deals.json` for production freshness.

### Coupon checker ops

After deploying the resolver-tier batch (`git pull origin main && docker compose up -d --build`), verify a full cycle against the current `CHANGELOG.md` entry (`[unreleased] coupon-checker hardening`):

- **Post-deploy:** `git rev-parse HEAD` equals the pushed SHA; `docker compose ps` shows a new `Started` time for `coupon-checker`; the first `=== Coupon check cycle start ===` appears after that timestamp; `docker compose logs coupon-checker | grep -c discountCode` is `0` (coupon codes never logged).
- **Pass criteria:** error share ≤ 10% (≤ 38 of 380 deals); expired share within ±5 points of the pre-deploy baseline; the 6 collision slugs + `situational_leadership` + >55-char slugs all resolve via some tier.
- **Deploy recipe** (full backup → reconcile → checkout/pull → recreate → verify sequence) is documented in that CHANGELOG entry. Back up the dirty tree before `git checkout .` and reconcile every dirty path against the batch file list.

For a pure validation cycle (skips the ~45-min scrape), set `CHECKER_SCRAPE_ON_CYCLE=false` in the server `.env`, recreate the `coupon-checker` service, and revert to `true` afterwards (see `.env.example`).

---

## Backup & Recovery

Your enrollment history and settings are stored in a local SQLite database (`data/udemy_enroller.db` or `./udemy_enroller.db` locally; Docker volume path `/app/data/udemy_enroller.db`). Prefer the **automated** script (WAL-safe `sqlite3 .backup`, integrity check, retention) over a raw `cp`.

Full ops runbook: **[docs/ops/backup-restore.md](docs/ops/backup-restore.md)**.

### Automated backup
```bash
# Detects DB path from DB_PATH / DATABASE_URL / .env / common defaults
./scripts/backup_sqlite.sh              # writes backups/udemy_enroller-<UTC>.db
./scripts/backup_sqlite.sh drill        # non-destructive backup + restore round-trip
```

Typical cron (daily):
```cron
15 3 * * * cd /path/to/udemy_enroller && ./scripts/backup_sqlite.sh backup
```

### Restore (scripted)
```bash
# Stop writers first (local process or: docker compose stop web coupon-checker)
CONFIRM=YES ./scripts/backup_sqlite.sh restore backups/udemy_enroller-YYYYMMDDTHHMMSSZ.db
# Then restart the app / docker compose up -d
```

### Manual fallback
```bash
# Local (stop the app first when possible)
cp udemy_enroller.db udemy_enroller.db.backup

# Docker host snapshot
docker compose cp web:/app/data/udemy_enroller.db ./udemy_enroller.db.backup
```

---

## Project Impact

- **Designed to automate** the manual process of finding and claiming free coupons
- **Live impact metrics** on the demo homepage and `/llms.txt` are computed from aggregate enrollment totals in the database (sum of per-user lifetime stats), using Udemy list prices — not hardcoded
- Scales to **hundreds of concurrent** coupon processing requests
- **100% open-source** and self-hostable

---

## SEO, AEO & GEO Features

This project implements modern search and AI discoverability standards:

| Endpoint | Purpose |
|----------|---------|
| `/sitemap.xml` | XML sitemap for search engine indexing |
| `/robots.txt` | Crawler directives with AI bot permissions |
| `/llms.txt` | Machine-readable AI profile with Q&A format |
| `/ai-profile.json` | Structured JSON-LD SoftwareApplication schema |
| `/humans.txt` | Human-readable team and tech stack info |
| `/faq` | FAQPage schema with rich snippet optimization |
| `/about` | BreadcrumbList schema with developer bio |
| `/guides` | BreadcrumbList schema for tutorial discovery |

These features ensure the project is discoverable by Google, Bing, ChatGPT, Perplexity, and other AI search engines.

---

## About the Developer

**[Madhu Dadi](https://madhudadi.in/profile/)** is an AI Engineer, RAG & Analytics Consultant with 10+ years of experience building production-grade AI systems, full-stack web applications, and marketing analytics platforms.

- **Portfolio:** [https://madhudadi.in](https://madhudadi.in)
- **Blog:** [https://madhudadi.in/blog](https://madhudadi.in/blog) - Technical articles on FastAPI, RAG, and automation
- **LinkedIn:** [https://www.linkedin.com/in/madhu-dadi-54684531](https://www.linkedin.com/in/madhu-dadi-54684531)
- **X / Twitter:** [https://x.com/madhu245](https://x.com/madhu245)

This project is part of a broader portfolio of open-source automation tools aimed at democratizing access to technology and education.

---

## Contributing

Contributions are welcome. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for setup, tests, PR expectations, and safety rules (no real Udemy abuse tests, no secret commits).

Short version:

1. Fork and branch from `main`
2. Install deps, run `ruff check .` and `pytest`
3. Open a focused Pull Request

Security issues: [SECURITY.md](SECURITY.md) (prefer private reporting).  
Owner/counsel process checklist (not legal advice): [docs/legal-counsel-review.md](docs/legal-counsel-review.md).

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Notable changes are listed in [CHANGELOG.md](CHANGELOG.md).

---

## Disclaimer

**⚠️ This project is NOT affiliated, endorsed, or connected with Udemy or any of its affiliates.** "Udemy" is a registered trademark of Udemy, Inc. This is an independent, open-source tool built for educational purposes. Users are solely responsible for ensuring their use complies with [Udemy's Terms of Use](https://www.udemy.com/terms/).

---

## Responsible Use & Risks

Using this tool involves interacting with Udemy's systems through automated means. Please read and understand the following:

### 📋 Platform Compliance
- This tool interacts with Udemy's enrollment endpoints using your own session tokens — the same endpoints the Udemy website uses. It does **not** use a documented public API.
- **You are solely responsible** for ensuring your use complies with [Udemy's Terms of Use](https://www.udemy.com/terms/).
- Automated activity may be subject to rate limiting, CAPTCHA challenges, or account restrictions by Udemy.
- The project maintainers cannot guarantee uninterrupted availability of any Udemy feature.

### 🔒 Credential Safety
- Your Udemy session cookies (`access_token`, `client_id`, `csrftoken`) are **encrypted** (Fernet) before storage on the instance running the app (self-hosted machine or hosted demo server).
- Your Udemy password is **never stored** — not even as a hash.
- Udemy credentials are sent only to Udemy — not sold or shared with third parties.
- On the **hosted demo**, only **Cookie Login** is available (`DEPLOYMENT_ENV=server`).
- Anonymous analytics (Google Tag Manager / GA4) load only after cookie consent.

### ⏳ Rate Limiting & Respectful Use
- The tool implements **deployment-aware rate limiting**:
  - Server mode: 6–15 seconds between requests
  - Local mode: 3–8 seconds between requests
- Circuit breakers pause enrollment if too many errors (403) are detected.
- These delays are designed to be respectful of Udemy's systems — **do not reduce them** to attempt faster enrollment.

### ⚠️ Known Limitations
- Coupon codes expire rapidly — sometimes within hours or minutes.
- Not all 100% off coupons result in successful enrollment.
- Udemy may change their enrollment flow at any time, which could break this tool.
- Impact metrics on the live site reflect aggregate enrollment totals across all users and are calculated using course list prices, not actual payments.
- No guarantee is made that any specific course or coupon will be available.

### 📝 Data Stored
The following data is stored in the database on your instance:
- **Encrypted** Udemy session cookies (access_token, client_id, csrftoken)
- Your user preferences (category filters, language, rating thresholds)
- Aggregated enrollment history and savings totals
- Session expiration timestamps

The following data is **never** stored:
- Your Udemy password
- Payment information
- Browser history or personal browsing data

### 🤖 Browser Automation & Scraping

This tool uses CloudScraper and Playwright to access coupon aggregator sites for discovering publicly available coupon codes. The tool:

- Implements respectful, deployment-aware rate limiting (3–15 seconds between requests)
- Does not solve or bypass CAPTCHAs
- Does not rotate proxies for evasion
- Does not perform mass scraping
- Blocks itself after consecutive errors (circuit breaker pattern)

---

## Keywords & Tags

Udemy Course Enroller, Free Udemy Courses, Automated Udemy Enrollment, Udemy Coupon Aggregator, FastAPI Project, Python Automation, CloudScraper, Web Scraping, Educational Tool, Open Source, Madhu Dadi, AI Developer, Full Stack Developer, Marketing Analytics, Self-Hosting, Docker, SQLite, SQLAlchemy, Tailwind CSS, Free Online Learning, Course Enrollment Automation.

---

<p align="center">Built with ❤ by <a href="https://madhudadi.in">Madhu Dadi</a></p>
