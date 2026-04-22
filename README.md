# 🚀 Udemy Enroller – Backend System

A production-ready backend system built with FastAPI to discover, aggregate, and manage publicly available course opportunities.

> ⚠️ Note: This project is built for educational purposes to explore backend systems, automation concepts, and production deployment.

---

## 🌐 Live Demo

- 🔗 https://udemyenroller.madhudadi.in

---

## 🌐 My Portfolio

- 🔗 https://www.madhudadi.in

---

## 🧠 Problem Statement

While spending significant time on online learning platforms, I realized that many publicly available course opportunities (like discounts and offers) often go unnoticed due to timing and discoverability.

This project explores how to:

- Extract and structure web-based information  
- Build a system to manage and track opportunities  
- Deploy a production-ready backend system  

---

## ⚙️ Features

- 📊 Aggregates publicly available course data  
- 🔍 Filters and structures relevant opportunities  
- 🧾 Tracks history of processed data  
- ⚡ Real-time backend processing  
- 🌐 Web interface for monitoring and control  
- 🔒 Secure multi-tenant data isolation
- 🛠️ Robust automated schema repair and migrations

---

## 🏗️ Tech Stack

- **Backend:** FastAPI (Python 3.13)
- **Database:** SQLite + SQLAlchemy + Alembic
- **Automation:** Playwright
- **Containerization:** Docker, Docker Compose  
- **Web Server:** Nginx  
- **Monitoring:** Sentry, Structured JSON Logging
- **Security:** Bcrypt, CORS, Rate Limiting

---

## 🧱 Architecture

Client (Browser)
↓
Nginx (Reverse Proxy)
↓
FastAPI (Docker Container)
↓
SQLite Database (Persistent Volume)


---

## 🚀 Getting Started

### 🔹 Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Git

---

### 🔹 Clone Repository

```bash
git clone https://github.com/madhu2456/udemy_enroller_fastapi.git
cd udemy_enroller_fastapi
```

### 🔹 Deployment

```bash
# Start the container
docker compose up -d --build
```

The system automatically handles database migrations and schema repairs on startup via the custom entrypoint.

### 🔹 Frontend CSS Build (when templates/classes change)

```bash
npm install
npm run build:css
```

---

## 📊 Health Check

`GET /api/health`

---

## ⚠️ Disclaimer

This project is intended for educational purposes only.

---

## ⭐ Support

If you found this useful, consider giving it a ⭐ on GitHub!

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
