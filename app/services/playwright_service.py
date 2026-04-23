"""Asynchronous Playwright service for headless browser scraping."""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger
from app.core import constants

class PlaywrightManager:
    """Global manager for Playwright browser instance."""
    
    _pw = None
    _browser: Optional[Browser] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_browser(cls) -> Browser:
        async with cls._lock:
            if cls._browser is None:
                cls._pw = await async_playwright().start()
                cls._browser = await cls._pw.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        # Removes the "Chrome is being controlled by automated software"
                        # banner and strips navigator.webdriver from the browser object,
                        # preventing JS-based headless detection.
                        '--disable-blink-features=AutomationControlled',
                    ]
                )
                logger.info("Started global Playwright browser.")
            return cls._browser

    @classmethod
    async def close_browser(cls):
        async with cls._lock:
            try:
                if cls._browser:
                    # Use short timeout for faster shutdown
                    await asyncio.wait_for(cls._browser.close(), timeout=2.0)
                    cls._browser = None
                if cls._pw:
                    await asyncio.wait_for(cls._pw.stop(), timeout=1.0)
                    cls._pw = None
                logger.info("Stopped global Playwright browser.")
            except asyncio.TimeoutError:
                logger.warning("Playwright browser close timed out.")
                # Force cleanup of references anyway
                cls._browser = None
                cls._pw = None
            except Exception as e:
                logger.error(f"Error closing Playwright browser: {e}")
                cls._browser = None
                cls._pw = None


class PlaywrightService:
    """Manages Playwright browser contexts for scraping using the global pool."""

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self):
        browser = await PlaywrightManager.get_browser()
        proxy_config = {"server": self.proxy} if self.proxy else None
        
        self._context = await browser.new_context(
            user_agent=constants.DEFAULT_USER_AGENT,
            proxy=proxy_config,
            viewport={'width': 1280, 'height': 800},
            ignore_https_errors=True
        )
        # Add basic stealth scripts or flags if needed here
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._context:
            await self._context.close()

    async def get_page_content(self, url: str, wait_for_selector: Optional[str] = None) -> str:
        """Fetch the fully rendered HTML of a page."""
        if not self._context:
            return ""
            
        page: Page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=30000)
            return await page.content()
        except Exception as e:
            logger.error(f"Playwright failed to fetch {url}: {type(e).__name__} - {e}")
            return ""
        finally:
            await page.close()


import sys
