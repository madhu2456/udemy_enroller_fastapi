"""Diagnostic script: run all scrapers in parallel with per-scraper timeouts."""

import asyncio
import sys

sys.path.insert(0, "F:\\Codes\\Claude\\Udemy Enroller")

from app.services.scraper import SCRAPER_REGISTRY, ScraperService


async def main():
    print("Udemy Enroller -- Live Scraper Diagnostic (Parallel + Per-Scraper Timeout)")
    print("=" * 70)
    
    svc = ScraperService(list(SCRAPER_REGISTRY.keys()))
    
    async def run_with_timeout(scraper, semaphore, timeout=60):
        try:
            await asyncio.wait_for(scraper.scrape(semaphore), timeout=timeout)
        except asyncio.TimeoutError:
            scraper.error = f"Timed out after {timeout}s"
            scraper.done = True
            print(f"  [!] {scraper.site_name} timed out after {timeout}s")
        except Exception as e:
            scraper.error = str(e)
            scraper.done = True
            print(f"  [!] {scraper.site_name} error: {e}")
    
    detail_semaphore = asyncio.Semaphore(15)
    tasks = [
        asyncio.create_task(run_with_timeout(s, detail_semaphore, 60))
        for s in svc.scrapers
    ]
    
    await asyncio.gather(*tasks, return_exceptions=True)
    await svc.close()
    
    print("\n" + "=" * 70)
    print(f"{'Scraper':<25} {'Found':>8} {'Listed':>8} {'Done':>6} {'Error':>8}")
    print("-" * 70)
    
    total_found = 0
    for p in svc.get_progress():
        scraper = svc.site_to_scraper[p['site']]
        found = len(scraper.data)
        total_found += found
        error_txt = (scraper.error or "")[:30]
        print(f"{p['site']:<25} {found:>8} {p['total']:>8} {'Yes' if p['done'] else 'No':>6} {error_txt:>8}")
        
        for i, c in enumerate(scraper.data[:2]):
            print(f"      [{i+1}] {c.title[:50]} | {c.url[:55]}")
        if len(scraper.data) > 2:
            print(f"      ... and {len(scraper.data) - 2} more")
    
    print("-" * 70)
    print(f"{'TOTAL UNIQUE':<25} {total_found:>8}")


if __name__ == "__main__":
    asyncio.run(main())
