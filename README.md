# Udemy Course Enroller - Automated Free Udemy Course Enrollment

* **Built by**: Madhu Dadi
* **Canonical profile**: https://madhudadi.in/profile/
* **Case study**: https://madhudadi.in/case-studies/udemy-enroller-fastapi/
* **Service relevance**: Python/FastAPI Automation & Data Engineering

---

> **⚠️ Disclaimer:** This project is **NOT affiliated, endorsed, or connected with Udemy or any of its affiliates.** "Udemy" is a registered trademark of Udemy, Inc. This is an independent, open-source tool built for educational purposes. Users are solely responsible for ensuring their use complies with [Udemy's Terms of Use](https://www.udemy.com/terms/).
>
> A free, open-source FastAPI application that automatically finds and enrolls you in 100% discounted Udemy courses. Built by [Madhu Dadi](https://madhudadi.in).

[![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python)](https://python.org)
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

**Udemy Course Enroller** is an asynchronous web application built with **Python** and **FastAPI** that automates the process of discovering and enrolling in free, 100% off discounted Udemy courses. It continuously monitors popular coupon aggregator websites - such as Real Discount, Discudemy, and Courson - and uses Udemy's enrollment endpoints to claim courses directly to your account.

No more manually hunting for expired coupons or missing limited-time offers. The tool runs in the background, filters courses based on your preferences, and builds you a library of premium educational content - completely free.

---

## Why This Exists

Premium online education on platforms like Udemy can be expensive. However, instructors frequently share **100% off coupons** on aggregator sites to build reviews and reach new students. The problem? These coupons expire within hours - sometimes minutes.

This tool solves that by:
- **Monitoring** multiple coupon sources 24/7
- **Filtering** courses by category, language, rating, and instructor
- **Enrolling** automatically via Udemy's enrollment endpoints
- **Tracking** your lifetime savings in real-time

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Fully Automated** | Set filters once, let the engine handle everything else |
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

- **Backend:** Python 3.13 + [FastAPI](https://fastapi.tiangolo.com) (async)
- **Database:** SQLite + [SQLAlchemy](https://www.sqlalchemy.org) ORM + Alembic migrations
- **Automation:** [CloudScraper](https://github.com/VeNoMouS/cloudscraper) (primary HTTP client for coupon sites and Udemy API) + [Playwright](https://playwright.dev/python/) with [playwright-stealth](https://github.com/Mattwmaster58/playwright_stealth) (fallback for Cloudflare-protected coupon aggregator sites)
- **Frontend:** HTML5 + [Tailwind CSS](https://tailwindcss.com) + vanilla JavaScript
- **Deployment:** Docker + docker-compose ready

The frontend is intentionally lightweight to ensure sub-second load times. Server-Sent Events (SSE) power the live log stream and enrollment progress updates.

---

## Quick Start

### Prerequisites
- Python 3.13+ (or Docker)
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

2. Generate and set a strong `SECRET_KEY` in a `.env` file:
   ```bash
   # Generate a secure 32-byte key
   openssl rand -hex 32
   ```

   Create a `.env` file:
   ```env
   SECRET_KEY=your_generated_strong_hex_key_here
   ```

3. Launch the container:
   ```bash
   docker-compose up -d
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
5. **Click "Start Enrollment"** on the Dashboard
6. **Watch** as courses are automatically claimed and tracked

For detailed setup instructions, visit the [Guides](https://udemyenroller.madhudadi.in/guides) page or read the [case study](https://madhudadi.in/case-studies/udemy-enroller-fastapi/).

---

## Validating Expired Coupons

The application includes a background script to automatically hit the Udemy pricing API and validate whether your scraped coupons are still active or have expired. This drives the public `/udemycoupons` deals page.

### Running Locally
If you are running the application locally via Python, simply run the bash script from the root directory:
```bash
./scripts/coupon_checker.sh
```

### Running on Production Server (Docker)
If you have deployed the application using Docker (e.g., via `scripts/deploy.sh`), you must run the checker *inside* the running container:
```bash
docker compose exec web bash ./scripts/coupon_checker.sh
```
*(Note: You can safely add this command to your server's cron jobs to automatically check coupon statuses daily.)*

---

## Backup & Recovery

Your enrollment history and settings are stored in a local SQLite database (`udemy_enroller.db`). To back up your data:

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
- **1,400+ courses** enrolled to date via automated enrollment
- **₹8,44,000+** estimated cost savings (based on list prices of enrolled courses)
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

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

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
- Your Udemy session cookies (`access_token`, `client_id`, `csrftoken`) are **encrypted** (Fernet) before storage in the local database.
- Your Udemy password is **never stored** — not even as a hash.
- Credentials are **never transmitted** to any third-party server.
- All data stays on your instance (local or self-hosted).

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
- The project's impact metrics ("1,400+ courses", "₹8,44,000+ savings") reflect aggregate data across all users and are calculated using course list prices, not actual payments.
- No guarantee is made that any specific course or coupon will be available.

### 📝 Data Stored
The following data is stored in the local database:
- **Encrypted** Udemy session cookies (access_token, client_id, csrftoken)
- Your user preferences (category filters, language, rating thresholds)
- Aggregated enrollment history and savings totals
- Session expiration timestamps

The following data is **never** stored:
- Your Udemy password
- Payment information
- Browser history or personal browsing data

### 🤖 Browser Automation & Scraping

This tool uses CloudScraper and Playwright (with optional stealth patches) to access coupon aggregator sites. These are used for legitimate purposes — discovering publicly available coupon codes. The tool:

- Implements respectful rate limiting (3–15 seconds between requests)
- Does not bypass CAPTCHAs
- Does not rotate proxies for evasion
- Does not perform mass scraping
- Blocks itself after consecutive errors (circuit breaker pattern)

---

## Keywords & Tags

Udemy Course Enroller, Free Udemy Courses, Automated Udemy Enrollment, Udemy Coupon Aggregator, FastAPI Project, Python Automation, CloudScraper, Web Scraping, Educational Tool, Open Source, Madhu Dadi, AI Developer, Full Stack Developer, Marketing Analytics, Self-Hosting, Docker, SQLite, SQLAlchemy, Tailwind CSS, Free Online Learning, Course Enrollment Automation.

---

<p align="center">Built with ❤ by <a href="https://madhudadi.in">Madhu Dadi</a></p>
