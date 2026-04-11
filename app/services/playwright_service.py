"""Asynchronous Playwright service for headless browser scraping."""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger


class PlaywrightService:
    """Manages Playwright browser instances for scraping."""

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self._pw = None
        self._browser: Optional[Browser] = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        proxy_config = None
        if self.proxy:
            proxy_config = {"server": self.proxy}

        self._browser = await self._pw.chromium.launch(
            headless=True,
            proxy=proxy_config
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def get_page_content(self, url: str, wait_for_selector: Optional[str] = None) -> str:
        """Fetch the fully rendered HTML of a page."""
        context: BrowserContext = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page: Page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=30000)
            return await page.content()
        except Exception as e:
            logger.error(f"Playwright failed to fetch {url}: {type(e).__name__} - {e}")
            return ""
        finally:
            await context.close()
