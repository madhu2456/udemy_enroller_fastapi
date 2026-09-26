# Udemy Course Enroller - Automated Free Course Enrollment

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Standalone Executables](https://img.shields.io/badge/Download-Standalone%20Executables-blueviolet?logo=windows&logoColor=white)](https://github.com/madhu2456/udemy_enroller_fastapi/releases)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Live-Demo-blue)](https://udemyenroller.madhudadi.in)

> **⚠️ Disclaimer & Platform Notice:** This project is an independent open-source educational tool and is **not affiliated with, endorsed by, or connected to Udemy, Inc.** "Udemy" is a registered trademark of Udemy, Inc. This application interacts with session-based enrollment endpoints (not an official public API). Automated access may conflict with [Udemy's Terms of Use](https://www.udemy.com/terms/). Users are solely responsible for ensuring compliance. Course availability, coupon validity, and enrollment success are **never guaranteed**.

**Udemy Course Enroller** is an asynchronous Python and FastAPI application that discovers 100% off Udemy coupons across 17 aggregator sources and automates enrollment when you initiate a run. Available via Modern Desktop GUI (`python gui.py`), Unified Rich CLI (`python cli.py`), or Web Dashboard (`python run.py`).

### Why This Exists
Premium online education on platforms like Udemy can be expensive. Instructors frequently distribute 100% off coupons on aggregator platforms to build reviews and initial student traction, but coupons typically expire within hours or minutes. Udemy Course Enroller bridges this gap by continuously monitoring aggregators and queueing legitimate enrollments before coupons lapse.

**Quick Navigation**:
[Architecture](#2-architecture--capabilities) • [Key Features](#key-features-matrix) • [Quick Start](#3-quick-start) • [UI Overview](#user-interface-overview) • [Authentication](#4-authentication--setup) • [CLI Cheatsheet](#5-unified-rich-cli-reference) • [Configuration](#configuration--environment-variables) • [Migrations](#pinned-database-migrations) • [Operations](#7-operations--administration) • [Responsible Use](#8-responsible-use--legal-compliance)

---

## 2. Architecture & Capabilities

Udemy Course Enroller runs on an asynchronous Python 3.11+ stack engineered for high throughput, safe local credential persistence, and zero-configuration desktop operation:
- **Backend & Async Core**: Python 3.11+ async engine with [FastAPI](https://fastapi.tiangolo.com) and Uvicorn.
- **Database & State**: SQLite with [SQLAlchemy](https://www.sqlalchemy.org) ORM and Alembic migrations.
- **Scraper Fleet**: [CloudScraper](https://github.com/VeNoMouS/cloudscraper) + [Playwright](https://playwright.dev/python/) with domain-partitioned pacing, RSC Flight parsing, and anti-zombie batching.
- **User Interfaces**: Native Desktop GUI ([CustomTkinter](https://customtkinter.tomschimansky.com)), Unified Headless CLI ([Typer](https://typer.tiangolo.com) + [Rich](https://rich.readthedocs.io)), and Web Dashboard ([Tailwind CSS](https://tailwindcss.com) + SSE live logs).

### Key Features Matrix

| Capability | Description |
|---|---|
| **17-Scraper Fleet** | High-throughput harvesting across 17 aggregator sources with up to 500 coupons per site via RSC Flight & SSR parsing |
| **1-Click Cookie Import** | Zero-lock SQLite extraction from Chrome, Edge, Firefox, Brave, and Opera with platform keychain decryption |
| **Modern Desktop GUI** | Native CustomTkinter desktop interface featuring Dark/Light themes, dual progress bars, and a 1,000-line FIFO log console |
| **Unified Headless CLI** | Robust terminal interface powered by Typer and Rich with 7 subcommands, CI pipe detection, and `--dry-run` simulation |
| **Rate-Limited Enrollment** | Courteous exponential backoff delays (3–8s local, 6–15s server) and circuit breakers protecting user accounts |
| **Live Savings Analytics** | Real-time tracking of claimed courses, total money saved based on Udemy list prices, and lifetime history |
| **Zero Passwords Handled** | Pure session-based cookie authentication; passwords are never solicited, transmitted, or stored |
| **Docker & Self-Hostable** | Production-ready compose configuration with automated background coupon verification and health checks |

### 17-Scraper Fleet Summary

| # | Aggregator | Identifier | Extraction Engine & Strategy |
|---|---|---|---|
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
| 12 | **iDownloadCoupon**| `idc` | WooCommerce Store REST API (`/wp-json/wc/store/v1/products`) |
| 13 | **Real Discount** | `rd` | Direct CDN REST API (`cdn.real.discount/api/courses`) 0-hop links |
| 14 | **OnlineCourses.ooo** | `oc` | RSS XML feed ingestion + ReHub fallback (disabled by default) |
| 15 | **FreebiesGlobal**| `fg` | Tag archive harvesting (`/tag/udemy-100-off/`) & direct card links |
| 16 | **GeeksGod** | `gg` | Paginated catalog harvesting & tracking parameter sanitization |
| 17 | **TutorialBar** | `tb` | Next.js React Server Components (RSC) Flight 0-hop extraction |

### Fleet Architecture Highlights
- **Capacity Scaling**: Standardized to harvest up to 500 latest active courses per scraper across all 17 sources.
- **Domain-Partitioned Pacing**: Domain-isolated delays eliminate cross-site bottlenecking while respecting aggregator hosts.
- **0-Hop Fast Resolution**: Direct coupon extraction via RSC Flight chunks, Angular SSR TransferState, and REST endpoints.
- **Anti-Zombie Chunking**: Concurrent detail resolution runs in discrete batches (`DETAIL_BATCH_SIZE = 10`) with immediate task cleanup.

---

## 3. Quick Start

Choose the setup path tailored to your workflow:

### System Prerequisites
- **Python Environment**: Python 3.11 or higher (for source installations).
- **Udemy Account**: An active account on [Udemy.com](https://www.udemy.com) (free registration).
- **Supported Browsers**: Chrome, Edge, Firefox, Brave, or Opera for automated cookie extraction.

### Option 1: Standalone Desktop App (Casual Users)
No Python installation or dependencies required:
1. Download the pre-compiled binary (`Gui.exe` for Windows, `Gui` for Linux/macOS) from **[GitHub Releases](https://github.com/madhu2456/udemy_enroller_fastapi/releases)**.
2. Double-click to launch the native desktop application.

### Option 2: Python Desktop GUI (Developers / Power Users)
Launch the native CustomTkinter GUI in two commands:
```bash
pip install -r requirements.txt
python gui.py
```
> [!NOTE]
> On Linux, ensure `python3-tk` is installed (e.g., `sudo apt install python3-tk`). For headless or SSH environments, use the [Unified Rich CLI](#5-unified-rich-cli-reference).

### Option 3: Docker & Self-Hosting (Homelab / Server Users)
Deploy the web application and automated coupon checker with persistent storage:
```bash
git clone https://github.com/madhu2456/udemy_enroller_fastapi.git && cd udemy_enroller_fastapi

# Generate required server secrets into .env to prevent container boot crash (using stdlib secrets/base64 keygen)
python3 -c 'import secrets, base64; print(f"SECRET_KEY={secrets.token_hex(32)}\nCOOKIE_ENCRYPTION_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}\nDEPLOYMENT_ENV=server")' > .env

docker compose up -d --build
```
Access the web dashboard at `http://localhost:8000`.

### Option 4: Local Web Server (Development)
```bash
git clone https://github.com/madhu2456/udemy_enroller_fastapi.git && cd udemy_enroller_fastapi
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

### Compiling Standalone Executables Locally
Compile native standalone binaries (`Gui.exe` / `cli.exe`) using PyInstaller:
```bash
pip install pyinstaller
python build_exe.py --all   # Builds both Desktop GUI and Unified CLI into dist/
```

### User Interface Overview

Udemy Course Enroller provides rich visual feedback across both desktop and web interfaces:

* **Modern Desktop GUI (`python gui.py`)**:
  * **Dual Concurrent Progress Bars**: Visualizes high-level aggregator scraping completion simultaneously with granular course enrollment checkout batches.
  * **1,000-Line FIFO Console**: Embedded circular log viewer backed by `collections.deque` with log-level color tagging, auto-scroll lock, and dynamic execution pause/resume.
  * **Interactive Scraper Grid**: Checkbox matrix allowing granular source isolation, batch toggles (*"Select All"*, *"Deselect All"*), and status indicators.
  * **Thread-Safe Architecture**: Asynchronous backend tasks communicate with CustomTkinter through thread-safe `command_queue` and `event_queue` channels.

* **Web Dashboard (`python run.py`)**:
  * **Server-Sent Events (SSE)**: Sub-second real-time streaming of backend log events and scraper progress directly to the browser UI without page reloads.
  * **Live Savings Analytics**: Interactive metrics dashboard showing cumulative courses claimed, financial savings based on Udemy list prices, and category breakdowns.
  * **Lightweight Responsive Design**: Clean Tailwind CSS interface with zero heavy frontend framework overhead for optimal responsiveness.

---

## 4. Authentication & Setup

Udemy Enroller authenticates using session cookies. Your password is **never** requested, handled, or stored.

### 1-Click Safe Browser Cookie Import (Recommended)
The built-in cookie importer (`app/services/browser_cookies.py`) extracts active Udemy credentials (`access_token`, `client_id`, `csrftoken`) directly from your browser:
* **Supported Browsers**: Google Chrome, Microsoft Edge, Mozilla Firefox, Brave Browser, Opera & Opera GX, Chromium.
* **Zero-Lock Extraction**: Copies cookie stores to a temporary directory and queries using SQLite immutable mode (`mode=ro&immutable=1`), never locking your active browser.
* **Platform Security**: Automatically decrypts credentials using Windows DPAPI, Linux SecretService/Keyring, or macOS Keychain.
* **Usage**: Click **"Extract from Browser"** on the GUI or execute `python cli.py login`.

### Browser Cookie Troubleshooting & Platform Guidance

If automated extraction fails or returns missing tokens, check the following platform considerations:

1. **Active Browser Session Required**:
   * You must be actively logged into [Udemy.com](https://www.udemy.com) in your target browser.
   * Browsers only persist session cookies to SQLite disks after initial authentication. If you recently logged in, keep the browser open or restart it to flush cookie caches.
2. **Windows Chrome 127+ App-Bound Encryption (`v20`)**:
   * Starting with Chrome version 127 on Windows, Google introduced App-Bound Encryption (`v20`), locking master decryption keys to system service contexts that standard user-level processes cannot decrypt via standard DPAPI.
   * **Recommended Workaround (Seamless)**: Use **Mozilla Firefox** or **Microsoft Edge**. Firefox stores cookies in unencrypted SQLite (`moz_cookies`), and Edge utilizes standard Windows DPAPI, allowing 1-click import without friction.
   * **Alternative**: Export cookies from Chrome via developer tools or install a manual session exporter.
3. **Linux Keyring Permissions**:
   * On Linux distributions using GNOME Keyring or KWallet, grant permission if prompted during decryption key extraction. Headless servers should provide credentials via CLI flags or `.env`.
4. **macOS Keychain Access**:
   * macOS prompts for Keychain access upon first reading Chrome Safe Storage. Click **"Always Allow"** to prevent repeated OS dialogs.

<details>
<summary><b>Manual Cookie Extraction (Fallback via F12 DevTools)</b></summary>

If automated extraction is unavailable in your environment:
1. Log into [Udemy.com](https://www.udemy.com) in your browser.
2. Press `F12` to open Developer Tools and navigate to **Application** (Chrome/Edge) or **Storage** (Firefox) → **Cookies** → `https://www.udemy.com`.
3. Copy the values for `access_token`, `client_id`, and `csrftoken`.
4. Paste them into the GUI login form or authenticate via CLI:
   ```bash
   python cli.py login --token YOUR_TOKEN --client-id YOUR_ID --csrf YOUR_CSRF
   ```
</details>

> [!TIP]
> For headless servers or automated CI runners where browser access is impossible, extract the session cookies on your local machine and pass them to the server via `.env` or the CLI `--token` flag.

---

## 5. Unified Rich CLI Reference

The CLI (`cli.py`), powered by Typer and Rich, provides complete headless operation, automated batch runs, and CI/CD integration:

```bash
python cli.py --help
```

### CLI Command Cheatsheet

| Command | Purpose | Example Usage |
|---|---|---|
| `login` | Authenticate & persist session to encrypted storage | `python cli.py login --browser chrome` |
| `logout` | Purge saved credentials from local storage | `python cli.py logout` |
| `enroll` | Harvest coupons and execute bulk enrollment | `python cli.py enroll --limit 30 --workers 6` |
| `scrape` | Harvest coupons only (no enrollment requests) | `python cli.py scrape --sites "Courson,TutorialBar" --format json` |
| `check` | Verify session health or probe coupon URL validity | `python cli.py check` or `python cli.py check --url "<url>"` |
| `stats` | View account metrics, total enrollments & savings | `python cli.py stats --output stats.json` |
| `server` | Launch FastAPI web server via Uvicorn | `python cli.py server --host 0.0.0.0 --port 8000` |
| *Flags* | Global concurrency, filtering & testing options | `--dry-run`, `--workers 6`, `--min-rating 4.2`, `--categories "IT"` |

### Filtering & Execution Flags Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--dry-run` | Flag | `False` | Simulates scraping and rule evaluation without making enrollment requests |
| `--workers`, `-w` | Integer | `6` | Number of concurrent site scrapers (overrides `MAX_SCRAPER_WORKERS`) |
| `--limit`, `-l` | Integer | `0` (all) | Maximum number of eligible courses to enroll in during a single run |
| `--min-rating` | Float | `0.0` | Minimum instructor rating filter threshold (e.g. `4.2`) |
| `--categories` | String | None | Comma-separated list of target course categories to include |
| `--languages` | String | None | Comma-separated list of course spoken languages to accept |
| `--output`, `-o` | Path | None | Export execution logs or scraped deals to JSON or CSV file |

### Practical CLI Workflows

```bash
# Dry-run simulation (scrape and match filters without enrolling)
python cli.py enroll --dry-run --categories "Development,IT & Software"

# Headless enrollment with 6 workers and rating threshold
python cli.py enroll --limit 25 --workers 6 --min-rating 4.0 --output results.json

# Export active scraped coupons across specific sites to CSV
python cli.py scrape --sites "Courson,TutorialBar,CouponScorpion" --format csv --output deals.csv
```

---

## 6. Configuration & Database Migrations

### Configuration & Environment Variables

Configure application behavior via `.env` or system environment variables:

| Variable | Default | Purpose & Description |
|---|---|---|
| `SECRET_KEY` | *Required in server* | Cryptographic salt for session signatures and CSRF protection. In `server` mode, boot fails if set to default placeholder. |
| `COOKIE_ENCRYPTION_KEY` | *Required in server* | 32-byte url-safe base64-encoded Fernet key used to derive per-session encryption keys (HKDF-SHA256) for stored cookies. |
| `DEPLOYMENT_ENV` | `local` | Environment profile (`local` or `server`). `server` mode enforces strict secrets, secure cookie flags, and disables user proxy overrides. |
| `MAX_SCRAPER_WORKERS` | `6` | Maximum concurrent scraper site workers executing simultaneously during catalog harvesting (CLI override: `--workers`). |
| `DATABASE_URL` | `sqlite:///./udemy_enroller.db` | SQLAlchemy connection URI. Supports SQLite (`sqlite:///./path.db`) or PostgreSQL (`postgresql://user:pass@host:5432/db`). |
| `COUPON_CHECKER_INTERVAL_SECONDS` | `7200` | Interval in seconds between automated public deal re-validation cycles executed by the `coupon-checker` companion service. |
| `PUBLIC_DEALS_PATH` | `./public_deals.json` | Filesystem path for validated public deals catalog. Set to `/app/data/public_deals.json` in Docker deployments. |
| `LOG_LEVEL` | `WARNING` | Application logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Keep at `WARNING` in production to prevent token exposure. |

Generate required keys easily with standard command-line tools:
```bash
# Generate SECRET_KEY
openssl rand -hex 32

# Generate COOKIE_ENCRYPTION_KEY (using standard library)
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

### Pinned Database Migrations
Always apply schema migrations using the pinned runner to guarantee database integrity against drift:

```bash
LIVE_ABS="$PWD/udemy_enroller.db"
touch "$LIVE_ABS"
python scripts/alembic_upgrade_pinned.py "$LIVE_ABS" head
```

> [!WARNING]
> Never run bare unpinned migrations (`alembic upgrade head`) directly against production databases. Always invoke `scripts/alembic_upgrade_pinned.py` with an absolute database path.

### Updating to Latest Version

**Local (git + venv):**
```bash
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
LIVE_ABS="$PWD/udemy_enroller.db"
python scripts/alembic_upgrade_pinned.py "$LIVE_ABS" head
python run.py
```

**Docker:**
```bash
git pull origin main
docker compose up -d --build
```

---

## 7. Operations & Administration

### Automated Backup & Recovery
Your enrollment history and settings are stored in SQLite (`udemy_enroller.db` or Docker volume `/app/data/udemy_enroller.db`). Automated WAL-safe backups are provided via `scripts/backup_sqlite.sh`:

```bash
./scripts/backup_sqlite.sh backup     # Generates backups/udemy_enroller-<UTC>.db
./scripts/backup_sqlite.sh drill      # Non-destructive backup + restore verification
```

Automated scheduled backups can be established via cron:
```cron
15 3 * * * cd /path/to/udemy_enroller && ./scripts/backup_sqlite.sh backup
```

To restore a previous backup snapshot:
```bash
CONFIRM=YES ./scripts/backup_sqlite.sh restore backups/udemy_enroller-YYYYMMDDTHHMMSSZ.db
```

For complete disaster recovery, restore drills, and retention policies, consult the **[Backup & Recovery Runbook](docs/ops/backup-restore.md)** and **[Security Key Rotation Runbook](docs/security-trio-fix.md)**.

### Background Coupon Checker
In Docker deployments, a companion `coupon-checker` service runs every 2 hours (default 7200s), re-validating cached deals against Udemy without touching the user database.

* **Catalog Maintenance**: Reads `public_deals.json`, probes Udemy endpoints, drops expired coupons, and updates the public catalog without touching personal user tables.
* **Trigger Immediate Check**:
  ```bash
  docker compose exec -T coupon-checker python -u scripts/coupon_checker.py
  ```

### Teardown & Uninstallation
* **Local**: Terminate the process (`Ctrl+C`) and delete the project directory.
* **Docker**: Stop and clean containers:
  ```bash
  docker compose down -v  # WARNING: -v destroys persistent database volumes
  ```

---

## 8. Responsible Use & Legal Compliance

### Compliance & Ethics Notice
* **Terms of Use**: This tool interacts with Udemy session-based endpoints using your own credentials. It does **not** use an official public API. Automated usage may violate [Udemy's Terms of Use](https://www.udemy.com/terms/). Users assume all platform risk.
* **Credential Protection**: Udemy session tokens (`access_token`, `client_id`, `csrftoken`) are encrypted on disk using AES/Fernet encryption. Your Udemy password is **never** handled, requested, or stored.
* **Courteous Rate Limiting**: Enforces built-in delays (3–8s locally, 6–15s in server mode) and circuit breaker trip thresholds. Do not reduce delays to flood endpoints.
* **Scraper Politeness**: Does not bypass CAPTCHAs, does not rotate malicious proxies, and partitions domain traffic to respect aggregator servers.
* **Guarantees**: 100% off coupons expire rapidly (often in minutes); enrollment success is never guaranteed.

### Contributing & Security
* **Contributing**: Contributions are welcome! Review **[CONTRIBUTING.md](CONTRIBUTING.md)** for testing guidelines (`ruff`, `pytest`) and contribution standards.
* **Security Issues**: Report security vulnerabilities privately per **[SECURITY.md](SECURITY.md)**. Legal process checklist available at [docs/legal-counsel-review.md](docs/legal-counsel-review.md).

### License & Author
* **License**: Licensed under the [MIT License](LICENSE).
* **Author**: Built by **[Madhu Dadi](https://madhudadi.in/profile/)** ([Website](https://madhudadi.in) • [Blog](https://madhudadi.in/blog) • [Case Study](https://madhudadi.in/case-studies/udemy-enroller-fastapi/) • [LinkedIn](https://www.linkedin.com/in/madhu-dadi-54684531) • [X/Twitter](https://x.com/madhu245)).
