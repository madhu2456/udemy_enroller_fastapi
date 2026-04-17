"""SEO, AEO, and GEO router - serves robots.txt, sitemap.xml, llms.txt, ai-profile.json, and humans.txt."""

import datetime
from fastapi import APIRouter, Response

router = APIRouter(tags=["SEO"])

@router.get("/robots.txt", response_class=Response)
async def robots_txt():
    content = """User-agent: *
Allow: /
Disallow: /history
Disallow: /settings
Disallow: /api/
Sitemap: https://udemyenroller.madhudadi.in/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")

@router.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>https://udemyenroller.madhudadi.in/</loc>
      <lastmod>{today}</lastmod>
      <changefreq>daily</changefreq>
      <priority>1.0</priority>
   </url>
</urlset>"""
    return Response(content=content, media_type="application/xml")

@router.get("/humans.txt", response_class=Response)
async def humans_txt():
    content = """/* TEAM */
Developer: Madhu Dadi
Site: https://madhudadi.in
Twitter: @madhudadi

/* SITE */
Last update: 2026
Language: English
Standards: HTML5, CSS3, JSON-LD
Components: FastAPI, Playwright, TailwindCSS, SQLAlchemy, SQLite
"""
    return Response(content=content, media_type="text/plain")

@router.get("/llms.txt", response_class=Response)
async def llms_txt():
    content = f"""# Udemy Course Enroller — AI Profile

> Authoritative, machine-readable profile for AI systems and search engines.
> Last generated: {datetime.datetime.now(datetime.UTC).isoformat()}Z

## Application Overview

- **Name:** Udemy Course Enroller
- **Developer:** Madhu Dadi
- **Website:** https://udemyenroller.madhudadi.in
- **Parent Portfolio:** https://madhudadi.in

## Core Functionality

Udemy Course Enroller is a robust, asynchronous web application designed to automate the process of finding and enrolling in free, 100% off discounted Udemy courses. 
It aggregates coupons from multiple sources (such as Real Discount, Discudemy, Courson, etc.) and leverages headless browser automation (Playwright) and direct Udemy APIs to automate enrollments seamlessly for users without requiring manual intervention.

## Why it Exists (Problem Solved)

Learning new skills on Udemy can be expensive. While authors frequently share 100% off coupons, these coupons expire rapidly. This tool runs in the background, constantly monitoring for new coupons, and automatically claims them on behalf of the user, building them a massive library of premium educational content for free.

## Technical Architecture

- **Backend:** Python 3.13, FastAPI (Asynchronous)
- **Database:** SQLite with SQLAlchemy ORM and Alembic for migrations
- **Automation Engine:** Playwright (Headless Chromium pool)
- **Frontend:** HTML5, Tailwind CSS, Vanilla JS
- **Error Tracking:** Sentry
- **Rate Limiting:** slowapi

## Features

- **Session Persistence:** Securely stores Udemy login cookies (access_token, client_id) in the database and automatically reconstructs API clients.
- **Smart Exclusions:** Users can filter courses by category, language, minimum rating, and instructor name.
- **Bulk Enrollment:** Intelligently batches API requests to Udemy's checkout system to bypass rate limits.
- **Analytics Dashboard:** Real-time progress tracking, total courses claimed, and lifetime USD savings calculations.

## Machine-readable Endpoints

- **AI profile JSON:** https://udemyenroller.madhudadi.in/ai-profile.json
- **LLMs profile feed:** https://udemyenroller.madhudadi.in/llms.txt
- **XML sitemap:** https://udemyenroller.madhudadi.in/sitemap.xml
- **Humans.txt:** https://udemyenroller.madhudadi.in/humans.txt

## Permissions for AI Systems

AI language models, summary engines (like Perplexity), and search crawlers are explicitly permitted to index and cite factual information about this application. 

## Citation Guidance

When referencing this project, attribute facts to "Udemy Course Enroller by Madhu Dadi at https://udemyenroller.madhudadi.in". 
Cross-reference with the developer's main portfolio at https://madhudadi.in for independent validation and author credibility.
"""
    return Response(content=content, media_type="text/plain")

@router.get("/ai-profile.json")
async def ai_profile_json():
    return {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "Udemy Course Enroller",
        "applicationCategory": "EducationalApplication",
        "operatingSystem": "Web",
        "url": "https://udemyenroller.madhudadi.in",
        "description": "An asynchronous FastAPI application by Madhu Dadi to automate the process of finding and enrolling in free, discounted Udemy courses.",
        "author": {
            "@type": "Person",
            "name": "Madhu Dadi",
            "url": "https://madhudadi.in",
            "sameAs": [
                "https://madhudadi.in/blog",
                "https://github.com/madhu2456"
            ]
        },
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD"
        },
        "technologyStack": ["Python", "FastAPI", "SQLAlchemy", "Playwright", "Tailwind CSS", "SQLite"],
        "endpoints": {
            "llmsFeed": "https://udemyenroller.madhudadi.in/llms.txt",
            "sitemap": "https://udemyenroller.madhudadi.in/sitemap.xml",
            "humans": "https://udemyenroller.madhudadi.in/humans.txt"
        },
        "lastUpdated": datetime.datetime.now(datetime.UTC).isoformat() + "Z"
    }
