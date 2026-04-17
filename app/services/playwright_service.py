"""Asynchronous Playwright service for headless browser scraping."""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger


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
                    args=['--disable-dev-shm-usage', '--no-sandbox']
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            proxy=proxy_config
        )
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
            await page.goto(url, wait_until="networkidle", timeout=60000)
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=30000)
            return await page.content()
        except Exception as e:
            logger.error(f"Playwright failed to fetch {url}: {type(e).__name__} - {e}")
            return ""
        finally:
            await page.close()


async def extract_udemy_cookies_interactive(timeout_seconds: int = 300) -> dict:
    """Launch a visible browser and poll for Udemy auth cookies."""
    logger.info("Launching interactive browser for cookie extraction...")
    
    async with async_playwright() as p:
        # Launch visible browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Navigate to Udemy login
        try:
            from app.core import constants
            await page.goto(constants.UDEMY_LOGIN_POPUP_URL, wait_until="networkidle")
        except Exception as e:
            logger.error(f"Failed to navigate to Udemy: {e}")
            await browser.close()
            return {}

        start_time = asyncio.get_event_loop().time()
        extracted_cookies = {}

        try:
            while asyncio.get_event_loop().time() - start_time < timeout_seconds:
                # Check if browser is still open
                if browser.is_connected() is False or len(browser.contexts) == 0:
                    break

                cookies = await context.cookies()
                cookie_map = {c["name"]: c["value"] for c in cookies if ".udemy.com" in c["domain"]}
                
                # We need access_token, client_id, and csrftoken
                access_token = cookie_map.get("access_token")
                client_id = cookie_map.get("client_id")
                csrf_token = cookie_map.get("csrftoken") or cookie_map.get("csrf_token")

                if access_token and client_id and csrf_token:
                    extracted_cookies = {
                        "access_token": access_token,
                        "client_id": client_id,
                        "csrf_token": csrf_token
                    }
                    logger.info("Successfully extracted Udemy cookies via interactive browser.")
                    break
                
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error during cookie polling: {e}")
        finally:
            await browser.close()
            
        return extracted_cookies
