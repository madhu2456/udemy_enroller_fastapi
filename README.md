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

---

## What is Udemy Course Enroller?

**Udemy Course Enroller** is an asynchronous web application built with **Python** and **FastAPI** that helps you discover free (often 100% off) Udemy course coupons and **attempt** enrollment when you start a run. While a run is active, it monitors configured coupon aggregator sites — such as Real Discount, Discudemy, and Courson — applies your filters, and uses session-based Udemy enrollment endpoints. Enrollment success and coupon validity are **not guaranteed**.

You can also browse public free-coupon listings without automation. Prefer self-hosting if you want full control over where session cookies are stored.

---

## Why This Exists

Premium online education on platforms like Udemy can be expensive. However, instructors frequently share **100% off coupons** on aggregator sites to build reviews and reach new students. The problem? These coupons expire within hours - sometimes minutes.

This tool helps with that by:
- **Monitoring** configured coupon sources when you start an enrollment run
- **Filtering** courses by category, language, rating, and instructor
- **Attempting enrollment** via Udemy's session-based enrollment endpoints (not guaranteed)
- **Tracking** recorded enrollments and estimated savings on the dashboard

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Run-based automation** | Set filters, start a run; the engine monitors sources while the run is active |
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

# Run migrations
alembic upgrade head

# Start the server
python run.py
```

The application will be available at `http://localhost:8000`.

### Option 2: Docker

By default, containerized deployments run in `DEPLOYMENT_ENV=server` mode to enforce strict production security. **The container will fail to start if you do not configure a strong, unique `SECRET_KEY`**.

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

## Updating

### Local (git + venv)

```bash
cd udemy_enroller_fastapi
git pull origin main
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
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

Production pushes to `main` can also deploy via **GitHub Actions** (`.github/workflows/deploy.yaml`), if that workflow is configured for your server.

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

**Either process updates `public_deals.json` and the coupon entries in `/sitemap.xml`:**

1. **Enrollment run** (Start Enrollment) — coupons are checked in the pipeline; when the run finishes, the JSON is rebuilt from DB rows with `is_coupon_valid=true`, then the sitemap deal URLs are refreshed.
2. **Standalone checker** — re-validates existing DB coupons and rebuilds the same JSON + sitemap.

`GET /sitemap.xml` always rebuilds from the current `public_deals.json` (valid slugs only). A disk snapshot is also written as `sitemap.generated.xml` / `sitemap.meta.json` after each export.

### Running Locally
From the project root:
```bash
./scripts/coupon_checker.sh
```

### Running on Production Server (Docker)
Run the checker *inside* the running container:
```bash
docker compose exec web bash ./scripts/coupon_checker.sh
```
*(Optional: schedule this via cron if you want periodic re-checks without starting an enrollment run.)*

---

## Backup & Recovery

Your enrollment history and settings are stored in a local SQLite database (`udemy_enroller.db` locally, or under the Docker data volume, e.g. `/app/data/udemy_enroller.db`). To back up your data:

### Manual Backup
```bash
# Stop the application first, then copy the database
cp udemy_enroller.db udemy_enroller.db.backup
```

### Docker Backup
```bash
# Copy the database from the running container
docker compose cp web:/app/data/udemy_enroller.db ./udemy_enroller.db.backup
```

### Restore
```bash
# Stop the application, replace the database, restart
cp udemy_enroller.db.backup udemy_enroller.db
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

**[Madhu Dadi](https://madhudadi.in)** is an AI Developer & Marketing Analytics Leader with 9+ years of experience building production-grade AI systems, full-stack web applications, and marketing analytics platforms.

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
