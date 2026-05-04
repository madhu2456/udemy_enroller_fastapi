# Udemy Course Enroller — Automated Free Udemy Course Enrollment

> A free, open-source FastAPI application that automatically finds and enrolls you in 100% discounted Udemy courses. Built by [Madhu Dadi](https://madhudadi.in).

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Live-Demo-blue)](https://udemyenroller.madhudadi.in)

**Live Demo:** [https://udemyenroller.madhudadi.in](https://udemyenroller.madhudadi.in)  
**Case Study:** [https://madhudadi.in/case-studies/udemy-enroller-fastapi/](https://madhudadi.in/case-studies/udemy-enroller-fastapi/)  
**Developer Portfolio:** [https://madhudadi.in](https://madhudadi.in) | **Blog:** [https://madhudadi.in/blog](https://madhudadi.in/blog)

---

## What is Udemy Course Enroller?

**Udemy Course Enroller** is an asynchronous web application built with **Python** and **FastAPI** that automates the process of discovering and enrolling in free, 100% off discounted Udemy courses. It continuously monitors popular coupon aggregator websites — such as Real Discount, Discudemy, and Courson — and uses Udemy's official API to claim courses directly to your account.

No more manually hunting for expired coupons or missing limited-time offers. The tool runs in the background, filters courses based on your preferences, and builds you a library of premium educational content — completely free.

---

## Why This Exists

Premium online education on platforms like Udemy can be expensive. However, instructors frequently share **100% off coupons** on aggregator sites to build reviews and reach new students. The problem? These coupons expire within hours — sometimes minutes.

This tool solves that by:
- **Monitoring** multiple coupon sources 24/7
- **Filtering** courses by category, language, rating, and instructor
- **Enrolling** automatically via Udemy's API
- **Tracking** your lifetime savings in real-time

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Fully Automated** | Set filters once, let the engine handle everything else |
| **Smart Filtering** | Exclude categories, languages, low-rated courses, or specific instructors |
| **Cookie-Based Auth** | Secure login using Udemy session cookies — no passwords stored |
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
- **Automation:** [CloudScraper](https://github.com/VeNoMouS/cloudscraper) (headless Chromium pool)
- **Frontend:** HTML5 + [Tailwind CSS](https://tailwindcss.com) + vanilla JavaScript
- **Monitoring:** Sentry error tracking + slowapi rate limiting
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

```bash
git clone https://github.com/madhu2456/udemy_enroller_fastapi.git
cd udemy_enroller_fastapi
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

## Project Impact

- **~90% reduction** in manual enrollment effort
- **20,000+ courses** enrolled collectively within 6 months
- **₹10,00,000+** estimated cost savings for active users
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
| `/about` | AboutPage schema with developer bio |
| `/guides` | CollectionPage schema for tutorial discovery |

These features ensure the project is discoverable by Google, Bing, ChatGPT, Perplexity, and other AI search engines.

---

## About the Developer

**[Madhu Dadi](https://madhudadi.in)** is an AI Developer & Marketing Analytics Leader with 9+ years of experience building production-grade AI systems, full-stack web applications, and marketing analytics platforms.

- **Portfolio:** [https://madhudadi.in](https://madhudadi.in)
- **Blog:** [https://madhudadi.in/blog](https://madhudadi.in/blog) — Technical articles on FastAPI, RAG, and automation
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

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Keywords & Tags

Udemy Course Enroller, Free Udemy Courses, Automated Udemy Enrollment, Udemy Coupon Aggregator, FastAPI Project, Python Automation, CloudScraper, Web Scraping, Educational Tool, Open Source, Madhu Dadi, AI Developer, Full Stack Developer, Marketing Analytics, Self-Hosting, Docker, SQLite, SQLAlchemy, Tailwind CSS, Free Online Learning, Course Enrollment Automation.

---

<p align="center">Built with ❤ by <a href="https://madhudadi.in">Madhu Dadi</a></p>
