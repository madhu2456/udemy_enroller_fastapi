"""Udemy API client for authentication and course enrollment - Asynchronous version."""

import json
import logging
import re
import asyncio
import random
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import unquote
from typing import Optional, Dict, List

import httpx
from bs4 import BeautifulSoup as bs
from loguru import logger

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.core import constants

# Known false-positive IDs from Udemy (e.g. tracking/user IDs appearing on blocked pages)
BLACKLIST_IDS = {"562413829"}


class LoginException(Exception):
    """Raised when Udemy login fails."""
    pass


class UdemyClient:
    """Handles asynchronous authentication and enrollment with the Udemy API."""

    def __init__(self, proxy: Optional[str] = None, firecrawl_api_key: Optional[str] = None):
        self.http = AsyncHTTPClient(proxy=proxy)
        self.firecrawl_api_key = firecrawl_api_key
        self.http.client.headers.update({
            "User-Agent": constants.DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{constants.UDEMY_BASE_URL}/",
        })

        self.display_name: str = ""
        self.currency: str = "usd"
        self.cookie_dict: dict = {}
        self.enrolled_courses: Optional[Dict[str, str]] = None

        # Enrollment counters
        self.successfully_enrolled_c = 0
        self.already_enrolled_c = 0
        self.expired_c = 0
        self.excluded_c = 0
        self.amount_saved_c = Decimal(0)

        self.is_authenticated = False

        # Persistent Playwright browser context — shared across ALL requests so that
        # Cloudflare clearance (cf_clearance) is solved once and stays valid for every
        # subsequent page.goto() / context.request call in this session.
        self._pw_context = None

        # True only after this Playwright context has itself navigated through a
        # Cloudflare challenge and earned its OWN cf_clearance cookie.  The user's
        # saved cf_clearance (from their desktop browser) has a different TLS
        # fingerprint and is invalid for Playwright's Chromium instance.
        self._pw_cf_clearance_earned = False

        # Session recovery tracking for 403 errors
        self.session_recovery_state = {
            "consecutive_403_errors": 0,
            "csrf_refresh_failures": 0,
            "cloudflare_challenges_encountered": 0,
            "last_error_time": None,
        }

    async def _get_persistent_pw_context(self):
        """Return the long-lived Playwright BrowserContext for this client.

        Creates the context on first call.  If the context has been closed or
        crashed, transparently recreates it so callers never need to handle that.
        """
        from app.services.playwright_service import PlaywrightManager

        if self._pw_context is not None:
            # Health-check: cookies() raises if the context is closed/crashed.
            try:
                await self._pw_context.cookies()
                return self._pw_context
            except Exception:
                logger.debug("Persistent Playwright context became invalid — recreating...")
                self._pw_context = None

        try:
            browser = await PlaywrightManager.get_browser()
            proxy_config = {"server": self.http.proxy} if self.http.proxy else None
            self._pw_context = await browser.new_context(
                user_agent=constants.DEFAULT_USER_AGENT,
                proxy=proxy_config,
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
            # Seed the fresh context with auth cookies so Udemy recognises the
            # session.  We intentionally EXCLUDE cf_clearance: the user's saved value
            # was issued to their desktop browser's TLS fingerprint (JA3/JA4) and
            # will be rejected by Cloudflare when presented from Playwright's Chromium.
            # Playwright will earn its own cf_clearance on first navigation.
            EXCLUDE_FROM_SEED = {"cf_clearance", "cf_bm", "__cf_bm"}
            if self.cookie_dict:
                seed_cookies = [
                    {"name": k, "value": v, "url": "https://www.udemy.com"}
                    for k, v in self.cookie_dict.items()
                    if v and isinstance(v, str)
                    and not k.startswith("_csrf_from")
                    and k not in EXCLUDE_FROM_SEED
                ]
                if seed_cookies:
                    await self._pw_context.add_cookies(seed_cookies)
            # Stealth init script: runs before every page's JavaScript so headless
            # detection heuristics (navigator.webdriver, plugins, languages) return
            # values indistinguishable from a real Chrome desktop session.
            await self._pw_context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const p = [
                            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                            {name: 'Native Client', filename: 'internal-nacl-plugin'},
                        ];
                        p.__proto__ = PluginArray.prototype;
                        return p;
                    }
                });
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                // Prevent iframe-based detection
                const _getContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                    const ctx = _getContext.apply(this, [type, ...args]);
                    return ctx;
                };
            """)
            logger.debug("Created new persistent Playwright context for UdemyClient")
        except Exception as e:
            logger.error(f"Failed to create persistent Playwright context: {e}")
            self._pw_context = None

        return self._pw_context

    async def _firecrawl_scrape(self, url: str, schema: Optional[Dict] = None, use_cookies: bool = True) -> Optional[Dict]:
        """Perform a stealthy scrape using Firecrawl API."""
        if not self.firecrawl_api_key:
            return None
            
        try:
            headers = {"Authorization": f"Bearer {self.firecrawl_api_key}", "Content-Type": "application/json"}
            payload = {"url": url}
            
            if schema:
                payload["params"] = {"extract": {"schema": schema}}
                
            if use_cookies and self.cookie_dict:
                cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookie_dict.items()])
                payload["pageOptions"] = {"headers": {"Cookie": cookie_str}}

            resp = await self.http.post("https://api.firecrawl.dev/v0/scrape", json=payload, headers=headers, req_type="api", log_failures=False)
            data = await self.http.safe_json(resp, "firecrawl request")
            
            if data and data.get("success") and "data" in data:
                return data["data"]
            return None
        except Exception as e:
            logger.debug(f"Firecrawl request failed for {url}: {e}")
            return None

    async def _page_goto_fetch(self, ctx, url: str, method: str) -> Optional[httpx.Response]:
        """Fetch a document URL via real ``page.goto()`` so JS-based CF challenges
        are solved inline.

        Navigates to the homepage first on the same page so the course URL fetch
        carries a proper ``Referer`` and matches a normal click-through pattern.
        CF hard-blocks direct deep-link navigations from headless browsers even
        with valid cf_clearance, so the prewarm is what makes course pages fetchable.

        Returns an httpx.Response-shaped object (status_code + content) so callers
        in get_course_id / check_course can keep using it the same way as the old
        ctx.request.get() flow.  Harvests cookies back into both the Playwright
        context (implicit) and self.http so the rest of the client keeps working.
        """
        page = None
        try:
            page = await ctx.new_page()

            # PREWARM: land on the homepage first.  This establishes nav history so
            # the following page.goto(course_url) sends `Referer: udemy.com/`, which
            # Cloudflare expects for a normal user clickthrough.  Without this, CF
            # WAF hard-403s deep-link navigations even when cf_clearance is valid.
            prewarm_needed = not self._pw_cf_clearance_earned
            if prewarm_needed:
                try:
                    await page.goto(
                        f"{constants.UDEMY_BASE_URL}/",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    await asyncio.sleep(1.0)
                    home_html = await page.content()
                    if await self._check_cloudflare_challenge(home_html):
                        logger.debug("  Prewarm hit CF challenge — waiting...")
                        for _ in range(10):
                            await asyncio.sleep(2)
                            home_html = await page.content()
                            if not await self._check_cloudflare_challenge(home_html):
                                break
                except Exception as prewarm_err:
                    logger.debug(f"  Prewarm navigation failed (continuing): {prewarm_err}")

            # Primary navigation.  Pass an explicit referer — `page.goto` only
            # auto-sets Referer from the previous page's URL when using the same
            # page, but being explicit avoids surprises when prewarm was skipped.
            resp = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
                referer=f"{constants.UDEMY_BASE_URL}/",
            )
            # Short settle so CF's post-challenge redirect / JS can run.
            await asyncio.sleep(1.5)

            html = await page.content()
            cf_challenge_was_seen = False

            # If CF challenge is on the page, wait up to ~20s for it to clear.
            if await self._check_cloudflare_challenge(html):
                cf_challenge_was_seen = True
                logger.debug(f"  Playwright page.goto hit CF challenge on {url} — waiting...")
                self.session_recovery_state["cloudflare_challenges_encountered"] += 1
                challenge_cleared = False
                for _ in range(10):
                    await asyncio.sleep(2)
                    html = await page.content()
                    if not await self._check_cloudflare_challenge(html):
                        logger.debug("  CF challenge cleared inline")
                        challenge_cleared = True
                        break
                if not challenge_cleared:
                    logger.warning(f"  CF challenge did not clear within 20s for {url}")
                    # Invalidate clearance so next refresh re-challenges.
                    self._pw_cf_clearance_earned = False
                    return httpx.Response(
                        status_code=403,
                        content=html.encode("utf-8", errors="replace"),
                        request=httpx.Request(method, url),
                    )

            # If a challenge was seen and then cleared, the initial goto response
            # status reflects the challenge page — it's stale.  We have real
            # content now, so report 200.  Otherwise use the actual goto status.
            if cf_challenge_was_seen:
                status = 200
            else:
                status = resp.status if resp else 200
            final_url = page.url

            # Harvest any fresh cookies (cf_clearance, csrftoken rotations, etc.).
            try:
                for c in await ctx.cookies():
                    if c.get("name") and c.get("value"):
                        self.cookie_dict[c["name"]] = c["value"]
                        self.http.client.cookies.set(c["name"], c["value"])
                        if c["name"] == "cf_clearance":
                            self._pw_cf_clearance_earned = True
            except Exception:
                pass

            if status != 200:
                # Log a snippet of the hard-block body so we can distinguish
                # CF 1020/Managed Challenge / rate-limit / origin 403.
                snippet = html[:400].replace("\n", " ") if html else ""
                logger.warning(
                    f"  Playwright page.goto {url} → {status}. "
                    f"CF challenge not detected. Body snippet: {snippet!r}"
                )
                # A 403 without a detectable challenge is a hard WAF block — drop
                # cf_clearance flag so the next refresh re-challenges from scratch.
                if status == 403:
                    self._pw_cf_clearance_earned = False

            return httpx.Response(
                status_code=status,
                content=html.encode("utf-8", errors="replace"),
                request=httpx.Request(method, final_url or url),
            )
        except Exception as e:
            logger.debug(f"Playwright page.goto failed for {url}: {e}")
            return None
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _playwright_request(self, url: str, method: str = "GET", data: Optional[Dict] = None, req_type: str = "xhr") -> Optional[httpx.Response]:
        """Perform a stealthy request using the persistent Playwright BrowserContext.

        GET (any req_type) → context.request.get() using Chromium TLS fingerprint.
            No JavaScript executes, so navigator.webdriver / headless detection
            cannot fire.  Cloudflare JS challenges are resolved separately by
            _refresh_csrf_stealth (page.goto to homepage) which earns cf_clearance
            into this context; that cookie is automatically sent here.
            Document requests use browser navigation headers; XHR/API requests use
            XHR headers.  Both return raw bytes.
        POST → warmup page navigation then context.request.post() (Chromium TLS
               fingerprint, immune to JS execution-context destruction).

        The persistent context means cf_clearance is earned once and reused for every
        subsequent request in this UdemyClient lifetime.  HTTPX is never used here so
        Python TLS fingerprints never reach Cloudflare-protected endpoints.
        """
        try:
            ctx = await self._get_persistent_pw_context()
            if ctx is None:
                logger.error("No Playwright context available — skipping stealthy request")
                return None

            csrf_token = (self.cookie_dict.get("csrf_token") or
                          self.cookie_dict.get("csrftoken", ""))

            headers_dict = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Token": csrf_token,
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
            }
            if method == "POST":
                headers_dict.update({
                    "Origin": constants.UDEMY_BASE_URL,
                    "Referer": f"{constants.UDEMY_BASE_URL}/payment/checkout/",
                })

            if method == "GET":
                # Document GETs (course landing pages) need real browser navigation:
                # ctx.request.get() sends cf_clearance but runs NO JavaScript, and
                # Cloudflare's per-path WAF can still 403 such requests even with a
                # valid clearance cookie.  page.goto() runs the full Chromium stack
                # so any inline CF challenge can be solved the same way the homepage
                # one was during _refresh_csrf_stealth.
                #
                # XHR/API GETs stay on ctx.request.get() — those are same-origin
                # requests from an already-cleared context and don't need a page.
                if req_type == "document":
                    return await self._page_goto_fetch(ctx, url, method)

                req_headers = headers_dict
                try:
                    pw_resp = await ctx.request.get(url, headers=req_headers, timeout=30000)
                    status = pw_resp.status
                    body = await pw_resp.body()
                    if status != 200:
                        logger.debug(f"  Playwright GET [{req_type}] {url} → {status}")
                        if status == 403:
                            # Log a snippet of the 403 body to distinguish CF hard-block
                            # from Udemy application 403.
                            snippet = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
                            logger.debug(f"  403 body snippet: {snippet}")
                    return httpx.Response(
                        status_code=status,
                        content=body,
                        request=httpx.Request(method, url),
                    )
                except Exception as req_err:
                    logger.debug(f"Playwright GET [{req_type}] failed for {url}: {req_err}")
                    return None

            else:  # POST
                # Warmup: navigate to cart/ in a real page so CF establishes clearance
                # for this context if it hasn't been used recently.
                page = await ctx.new_page()
                try:
                    await page.goto(
                        f"{constants.UDEMY_BASE_URL}/cart/",
                        wait_until="commit",
                        timeout=15000,
                    )
                    await asyncio.sleep(1)
                    for c in await ctx.cookies():
                        if c.get("name") and c.get("value"):
                            self.cookie_dict[c["name"]] = c["value"]
                            self.http.client.cookies.set(c["name"], c["value"])
                except Exception as nav_err:
                    logger.debug(f"Playwright warmup navigation failed (non-fatal): {nav_err}")
                finally:
                    await page.close()

                # Refresh CSRF token after warmup (warmup may have updated cookies)
                csrf_token = (self.cookie_dict.get("csrf_token") or
                              self.cookie_dict.get("csrftoken", ""))
                headers_dict["X-CSRF-Token"] = csrf_token

                try:
                    body_bytes = json.dumps(data).encode() if data else None
                    pw_resp = await ctx.request.post(
                        url, data=body_bytes, headers=headers_dict, timeout=30000
                    )
                    status = pw_resp.status
                    body = await pw_resp.body()
                    if status != 200:
                        logger.debug(f"  Playwright POST {url} → {status}")
                    return httpx.Response(
                        status_code=status,
                        content=body,
                        request=httpx.Request(method, url),
                    )
                except Exception as req_err:
                    logger.debug(f"Playwright POST request failed for {url}: {req_err}")
                    return None

        except Exception as e:
            logger.error(f"Playwright request failed for {url}: {e}")
            # Invalidate context so it's recreated fresh on next call.
            # Also reset cf_clearance flag — the new context must re-earn it.
            try:
                if self._pw_context:
                    await self._pw_context.close()
            except Exception:
                pass
            self._pw_context = None
            self._pw_cf_clearance_earned = False
            return None

    async def close(self):
        if self._pw_context is not None:
            try:
                await self._pw_context.close()
            except Exception:
                pass
            self._pw_context = None
            self._pw_cf_clearance_earned = False
        await self.http.close()

    def set_proxy(self, proxy: Optional[str]):
        """Update the proxy configuration."""
        if self.http.proxy != proxy:
            old_headers = self.http.client.headers
            old_cookies = self.http.client.cookies
            asyncio.create_task(self.http.close())
            self.http = AsyncHTTPClient(proxy=proxy)
            self.http.client.headers.update(old_headers)
            self.http.client.cookies.update(old_cookies)

    async def _check_cloudflare_challenge(self, html: str) -> bool:
        """Detect if page is Cloudflare challenge. Returns True if Cloudflare challenge detected."""
        # More specific indicators (cf_clearance alone isn't enough - it's set but challenge may persist)
        cloudflare_challenge_indicators = [
            'Just a moment',
            'challenge-platform',
            'Checking your browser before accessing',
            'cfrequests',
            'Ray ID',
        ]
        has_challenge = any(indicator in html for indicator in cloudflare_challenge_indicators)
        
        # Additional context: presence of auth indicators
        has_auth = any(indicator in html for indicator in ['_udemy_u', 'access_token', 'user-id'])
        
        # If challenge indicators present, it's definitely a challenge
        if has_challenge:
            logger.debug("Cloudflare challenge HTML indicators detected")
            return True
        
        # If no challenge indicators AND has auth, likely resolved
        if has_auth:
            logger.debug("Cloudflare challenge resolved - auth content detected")
            return False
        
        logger.debug("Cloudflare challenge status unclear - no specific indicators found")
        return False

    async def _extract_csrf_from_html(self, html: str) -> Optional[str]:
        """Extract CSRF token from HTML using various methods. Returns token value or None."""
        if not html:
            return None

        # Method 1: Look for csrftoken in meta tag
        meta_match = re.search(r'<meta[^>]*name=["\']csrftoken["\'][^>]*content=["\']([^"\']+)["\']', html)
        if meta_match:
            token = meta_match.group(1)
            logger.debug(f"Found CSRF token in meta tag: {token[:20]}...")
            return token

        # Method 2: Look for csrf_token in meta tag
        meta_match = re.search(r'<meta[^>]*name=["\']csrf_token["\'][^>]*content=["\']([^"\']+)["\']', html)
        if meta_match:
            token = meta_match.group(1)
            logger.debug(f"Found csrf_token in meta tag: {token[:20]}...")
            return token

        # Method 3: Look for CSRF token in script data (flexible pattern)
        script_match = re.search(r'["\']?csrf["\']?\s*:\s*["\']([a-f0-9\-]{20,})["\']', html, re.IGNORECASE)
        if script_match:
            token = script_match.group(1)
            logger.debug(f"Found CSRF token in script: {token[:20]}...")
            return token

        # Method 4: Look for X-CSRFToken or similar in script (flexible pattern)
        script_match = re.search(r'["\']?X-CSRF-?Token["\']?\s*:\s*["\']([a-f0-9\-]{20,})["\']', html, re.IGNORECASE)
        if script_match:
            token = script_match.group(1)
            logger.debug(f"Found X-CSRFToken in script: {token[:20]}...")
            return token

        # Method 5: Look for CSRF in any data attribute or hidden input
        input_match = re.search(r'<input[^>]*name=["\']csrf(?:token)?["\'][^>]*value=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if input_match:
            token = input_match.group(1)
            logger.debug(f"Found CSRF in hidden input: {token[:20]}...")
            return token

        return None

    async def _extract_csrf_with_retries(self, page, max_retries: int = 2) -> Optional[str]:
        """Extract CSRF token from page with retries. Handles dynamic loading."""
        for attempt in range(max_retries):
            try:
                # Wait for page to settle
                await asyncio.sleep(1)
                html_content = await page.content()

                # Try extract from HTML
                csrf_token = await self._extract_csrf_from_html(html_content)
                if csrf_token:
                    logger.info(f"Successfully extracted CSRF from HTML (attempt {attempt + 1})")
                    return csrf_token

                # Try to trigger any pending XHR requests by waiting
                if attempt < max_retries - 1:
                    logger.debug(f"CSRF not found, waiting for page to fully load (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(2)

                    # Try to wait for any pending requests
                    try:
                        await page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass  # Timeout is ok, just a wait hint
            except Exception as e:
                logger.debug(f"CSRF extraction attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.warning(f"CSRF extraction failed after {max_retries} attempts")
                    return None

        return None

    async def _refresh_csrf_stealth(self, force_full: bool = False) -> bool:
        """Refresh CSRF token and all session cookies using the persistent Playwright context.

        If ``force_full`` is True, the CSRF-header fast path is skipped and the
        existing ``cf_clearance`` is treated as invalid — callers reacting to an
        observed 403 should pass this so the context re-navigates through any
        Cloudflare challenge instead of just rotating a header.
        """
        logger.info(
            "Stealth: Refreshing CSRF token and cookies via Playwright..."
            + (" (forced full refresh)" if force_full else "")
        )
        csrf_found = False
        try:
            if force_full:
                # A prior 403 proved the current cf_clearance isn't good enough for
                # the protected path we're trying to hit.  Drop the flag so the
                # Playwright flow below re-runs the CF challenge.
                self._pw_cf_clearance_earned = False

            # FAST PATH: Reuse the login CSRF token only when Playwright's OWN context
            # has already earned a cf_clearance via a real browser navigation.  The
            # user's saved cf_clearance is TLS-fingerprint-bound to their desktop
            # browser and will NOT work in Playwright.  self._pw_cf_clearance_earned
            # is only set to True after a successful full navigation below.
            login_csrf = self.cookie_dict.get("csrf_token_login")
            if not force_full and login_csrf and self._pw_cf_clearance_earned:
                try:
                    logger.info("Fast path: reusing login CSRF token (Playwright cf_clearance already earned)...")
                    self.http.client.headers['X-CSRFToken'] = login_csrf
                    self.http.client.headers['X-CSRF-Token'] = login_csrf
                    self.cookie_dict['csrf_token'] = login_csrf
                    logger.info(f"Using login CSRF token as primary (length: {len(login_csrf)})")
                    return True
                except Exception as e:
                    logger.warning(f"Login CSRF token fast path error: {e}. Falling back to full refresh...")

            # FULL STRATEGY: Navigate to udemy.com using the persistent context so
            # Cloudflare issues (or re-validates) cf_clearance, and we pick up a fresh
            # csrftoken cookie in the same pass.
            if not self._pw_cf_clearance_earned:
                logger.info("Playwright context has no cf_clearance yet — full session refresh needed...")
            else:
                logger.debug("Refreshing CSRF + session cookies via Playwright...")

            ctx = await self._get_persistent_pw_context()
            if ctx is None:
                logger.error("Cannot refresh session — no Playwright context available")
                self.session_recovery_state["csrf_refresh_failures"] += 1
                return False

            cookies = []
            for strategy_attempt in range(3):
                if strategy_attempt == 1:
                    logger.info("Trying alternate Cloudflare resolution strategy (attempt 2/3)...")
                elif strategy_attempt == 2:
                    logger.info("Trying fresh browser context strategy (attempt 3/3)...")
                    # Last resort: recreate the persistent context entirely.
                    # Reset cf_clearance flag — the new context must earn it fresh.
                    try:
                        await self._pw_context.close()
                    except Exception:
                        pass
                    self._pw_context = None
                    self._pw_cf_clearance_earned = False
                    ctx = await self._get_persistent_pw_context()
                    if ctx is None:
                        break

                page = await ctx.new_page()
                try:
                    await page.goto(
                        f"{constants.UDEMY_BASE_URL}/",
                        wait_until="commit",
                        timeout=30000,
                    )
                    await asyncio.sleep(2)

                    html_content = await page.content()
                    is_cf_challenge = await self._check_cloudflare_challenge(html_content)

                    if is_cf_challenge:
                        logger.warning(f"Cloudflare challenge detected (strategy {strategy_attempt + 1}/3). Waiting...")
                        self.session_recovery_state["cloudflare_challenges_encountered"] += 1
                        challenge_resolved = False

                        for wait_attempt in range(15):
                            await asyncio.sleep(2)
                            html_content = await page.content()
                            if not await self._check_cloudflare_challenge(html_content):
                                logger.info(f"CF challenge resolved after {(wait_attempt + 1) * 2}s")
                                challenge_resolved = True
                                break

                        if not challenge_resolved:
                            logger.warning("CF challenge persisted 30s. Trying page reload...")
                            try:
                                await page.reload(wait_until="commit", timeout=30000)
                                await asyncio.sleep(3)
                                html_content = await page.content()
                                if not await self._check_cloudflare_challenge(html_content):
                                    logger.info("Challenge resolved after page reload")
                                    challenge_resolved = True
                            except Exception as reload_err:
                                logger.debug(f"Page reload failed: {reload_err}")

                        if not challenge_resolved:
                            logger.warning(f"Challenge unresolved after strategy {strategy_attempt + 1}. Trying next...")
                            continue

                    # Harvest all cookies from the context
                    cookies = await ctx.cookies()
                    cf_clearance_found = False
                    for c in cookies:
                        self.http.client.cookies.set(c["name"], c["value"])
                        self.cookie_dict[c["name"]] = c["value"]
                        if c["name"] in ("csrftoken", "csrf_token"):
                            logger.info(f"SUCCESS: Found {c['name']} in cookies!")
                            csrf_found = True
                        if c["name"] == "cf_clearance":
                            cf_clearance_found = True
                            # Mark that THIS Playwright context has its own valid
                            # cf_clearance — safe to use the CSRF fast path now.
                            self._pw_cf_clearance_earned = True
                            logger.info("✓ Playwright context earned its own cf_clearance")

                    if csrf_found:
                        logger.info("✓ CSRF token found in cookies - refresh successful")
                        break

                    # CSRF still missing: try extracting from page HTML
                    if not csrf_found:
                        csrf_token_val = await self._extract_csrf_with_retries(page, max_retries=2)
                        if csrf_token_val:
                            self.http.client.headers["X-CSRFToken"] = csrf_token_val
                            self.cookie_dict["_csrf_from_html"] = csrf_token_val
                            logger.info("Success: Extracted CSRF from HTML")
                            csrf_found = True
                            break
                        else:
                            logger.warning("Could not find CSRF token in HTML after retries")

                    if csrf_found:
                        break

                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

            if not csrf_found:
                logger.error("No fresh CSRF token found after all strategies.")
                self.session_recovery_state["csrf_refresh_failures"] += 1
                all_ctx_cookies = cookies or []
                has_auth = any(
                    any(n in c["name"].lower() for n in ("auth", "access", "sessionid", "jwt"))
                    for c in all_ctx_cookies
                )
                if not has_auth:
                    logger.error("CRITICAL: No auth cookies — user needs to log in again.")
                else:
                    logger.warning("Auth cookies present but CSRF refresh failed. Session may be temporarily blocked.")
                    logger.info("Recommendation: Wait 30-60 s, then retry.")

            if csrf_found:
                logger.info("CSRF token refresh successful")
                self.session_recovery_state["consecutive_403_errors"] = 0
            else:
                logger.error("CSRF token refresh failed after all attempts")

            return csrf_found
        except Exception as e:
            logger.error(f"Failed to refresh CSRF via Playwright: {e}")
            self.session_recovery_state["csrf_refresh_failures"] += 1
            return False

    async def manual_login(self, email: str, password: str):
        """Asynchronously login using email and password."""
        logger.info(f"Attempting manual login for {email}")
        try:
            r = await self.http.get(
                constants.UDEMY_SIGNUP_POPUP_URL,
                headers={"User-Agent": constants.DEFAULT_USER_AGENT},
                randomize_headers=False,
                req_type="document"
            )
            if not r:
                raise LoginException("Could not connect to Udemy.")

            csrf_token = r.cookies.get("csrftoken")
            if not csrf_token:
                raise LoginException("Email/password login is currently restricted by Udemy security.")

            data = {
                "csrfmiddlewaretoken": csrf_token,
                "locale": "en_US",
                "email": email,
                "password": password,
            }

            self.http.client.cookies.update(r.cookies)
            self.http.client.headers.update({
                "Referer": constants.UDEMY_LOGIN_POPUP_URL,
                "Origin": constants.UDEMY_BASE_URL,
            })

            resp = await self.http.post(
                constants.UDEMY_LOGIN_POPUP_URL,
                data=data,
                req_type="api"
            )

            if resp and "returnUrl" in resp.text:
                self.cookie_dict = {
                    "client_id": resp.cookies.get("client_id"),
                    "access_token": resp.cookies.get("access_token"),
                    "csrf_token": csrf_token,
                    "csrf_token_login": csrf_token,  # Save login token as fallback
                }
            else:
                error_data = await self.http.safe_json(resp, "login error")
                msg = error_data.get("error", {}).get("data", {}).get("formErrors", [["Unknown error"]])[0][0]
                raise LoginException(msg)

        except Exception as e:
            if isinstance(e, LoginException):
                raise
            logger.exception("Manual login failed")
            raise LoginException(f"Login failed: {str(e)}")

    def cookie_login(self, access_token: str, client_id: str, csrf_token: str):
        """Login using cookies (from browser)."""
        self.cookie_dict = {
            "client_id": client_id,
            "access_token": access_token,
            "csrf_token": csrf_token,
            "csrf_token_login": csrf_token,  # Save login token as fallback
        }
        self.http.client.cookies.update(self.cookie_dict)

    async def get_session_info(self):
        """Fetch session info asynchronously."""
        logger.info("Getting session info")
        try:
            headers = {"req_type": "api"}
            if self.cookie_dict.get("access_token"):
                headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

            resp = await self.http.get(
                constants.UDEMY_CONTEXT_URL,
                cookies=self.cookie_dict,
                headers=headers,
                randomize_headers=True,
                req_type="api"
            )
            ctx = await self.http.safe_json(resp, "session info")
            if not ctx or not ctx.get("header", {}).get("isLoggedIn"):
                raise LoginException("Login failed - session invalid.")

            self.display_name = ctx["header"]["user"]["display_name"]

            cart_resp = await self.http.get(
                constants.UDEMY_CART_URL,
                cookies=self.cookie_dict,
                headers=headers,
                randomize_headers=True,
                req_type="api"
            )
            cart = await self.http.safe_json(cart_resp, "cart info")
            if cart:
                self.currency = cart.get("user", {}).get("credit", {}).get("currency_code", "usd")

            self.is_authenticated = True
            logger.info(f"Authenticated as {self.display_name} ({self.currency.upper()})")

        except Exception as e:
            logger.exception("Failed to get session info")
            raise LoginException(f"Session verification failed: {str(e)}")

    async def get_enrolled_courses(self, known_slugs: set = None):
        """Fetch all enrolled courses in parallel pages. Stops early if known courses are found."""
        logger.info("Fetching enrolled courses...")
        base_url = f"{constants.UDEMY_SUBSCRIBED_COURSES_URL}?ordering=-enroll_time&fields[course]=enrollment_time,url&page_size=100"
        
        self.enrolled_courses = {}
        known_slugs = known_slugs or set()
        
        common_headers = {}
        if self.cookie_dict.get("access_token"):
            common_headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

        resp = await self.http.get(base_url, cookies=self.cookie_dict, headers=common_headers, req_type="api")
        data = await self.http.safe_json(resp, "enrolled courses page 1")
        if not data:
            return

        def process_results(results):
            stop = False
            for c in results:
                try:
                    parts = c["url"].split("/")
                    slug = parts[3] if len(parts) > 3 and parts[2] == "draft" else parts[2]
                    self.enrolled_courses[slug] = c.get("enrollment_time", "")
                    if slug in known_slugs:
                        stop = True
                except (IndexError, KeyError):
                    continue
            return stop

        if process_results(data.get("results", [])):
            logger.info(f"Fetched 1 page of enrolled courses (Reached known courses).")
            return

        batch_size = 5
        for start_page in range(2, 51, batch_size):
            tasks = []
            for page in range(start_page, start_page + batch_size):
                if page > 50: break
                url = f"{base_url}&page={page}"
                tasks.append(self.http.get(url, cookies=self.cookie_dict, headers=common_headers, req_type="api"))
            
            resps = await asyncio.gather(*tasks)
            any_stop = False
            for i, r in enumerate(resps):
                page_data = await self.http.safe_json(r, f"enrolled courses page {start_page + i}")
                if page_data and page_data.get("results"):
                    if process_results(page_data["results"]):
                        any_stop = True
                else:
                    any_stop = True
            
            if any_stop:
                logger.info(f"Reached known courses or end of list at batch starting page {start_page}.")
                break

        for slug in known_slugs:
            if slug not in self.enrolled_courses:
                self.enrolled_courses[slug] = ""
        logger.info(f"Enrolled courses check complete. Total tracked: {len(self.enrolled_courses)}.")

    def _extract_course_id(self, soup: bs) -> Optional[str]:
        """Extract course ID using multiple strategies."""
        BLACKLIST_IDS = {"562413829"}

        body = soup.find("body")
        if body:
            cid = body.get("data-clp-course-id") or body.get("data-course-id")
            if cid and str(cid) not in BLACKLIST_IDS:
                logger.debug(f"Found course ID {cid} via body data-attribute")
                return str(cid)

        meta_tags = [
            ("meta", {"property": "udemy_com:course"}),
            ("meta", {"name": "course-id"}),
            ("meta", {"property": "og:url"}),
        ]
        for tag, attrs in meta_tags:
            el = soup.find(tag, attrs)
            if el:
                content = el.get("content")
                if content and str(content) not in BLACKLIST_IDS:
                    if attrs.get("property") == "udemy_com:course" or attrs.get("name") == "course-id":
                        logger.debug(f"Found course ID {content} via meta tag {tag}")
                        return str(content)

        scripts = soup.find_all("script")
        for script in scripts:
            if not script.string:
                continue
            
            patterns = [
                (r'["\']?course["\']?\s*:\s*{\s*["\']?id["\']?\s*[:=]\s*(\d+)', "script course object id"),
                (r'["\']?visiting_course["\']?\s*:\s*{\s*["\']?id["\']?\s*[:=]\s*(\d+)', "script visiting_course object id"),
                (r'["\']?course_?id["\']?\s*[:=]\s*(\d+)', "script regex course_id"),
                (r'["\']?courseId["\']?\s*[:=]\s*(\d+)', "script regex courseId")
            ]
            for pattern, name in patterns:
                match = re.search(pattern, script.string, re.IGNORECASE)
                if match:
                    cid = match.group(1)
                    if cid and 4 < len(cid) < 12 and cid not in BLACKLIST_IDS:
                        logger.debug(f"Found course ID {cid} via {name}")
                        return cid

        return None

    async def get_course_id(self, course: Course, use_headless_fallback: bool = True):
        """Fetch course ID and metadata with Firecrawl-first, Playwright fallback chain."""
        if course.course_id:
            return
        url = re.sub(r"\W+$", "", unquote(course.url))
        
        if self.firecrawl_api_key:
            logger.info(f"Stealth: Fetching course ID for {course.title} via Firecrawl...")
            fc_schema = {"type": "object", "properties": {"course_id": {"type": "string"}, "title": {"type": "string"}}}
            fc_data = await self._firecrawl_scrape(url, schema=fc_schema)
            if fc_data and "extract" in fc_data:
                cid = fc_data["extract"].get("course_id")
                if cid and str(cid) not in BLACKLIST_IDS:
                    course.course_id = str(cid)
                    final_url = fc_data.get("metadata", {}).get("pageUrl")
                    if final_url and "udemy.com" in final_url:
                        logger.debug(f"  Firecrawl redirected to: {final_url}")
                        course.set_url(final_url)
                    
                    if course.coupon_code:
                        logger.debug(f"  Success: Found ID {course.course_id} and coupon via Firecrawl")
                        return
                    else:
                        logger.debug(f"  Firecrawl found ID {course.course_id} but no coupon. Continuing to fallback...")

        consecutive_403 = 0
        max_403_retries = 2
        resp = None
        playwright_cf_blocked = False  # True if Playwright hit CF 403 — skip raw HTTP fallback

        if use_headless_fallback:
            logger.info(f"Stealth: Fetching course ID for {course.title} via Playwright...")
            while consecutive_403 < max_403_retries:
                resp = await self._playwright_request(url, req_type="document")
                if resp and resp.status_code == 200:
                    final_url = str(resp.url)
                    logger.debug(f"  Playwright resolved to: {final_url}")
                    course.set_url(final_url)
                    soup = bs(resp.content, "lxml")
                    body = soup.find("body")
                    if body:
                        try:
                            dma = json.loads(body.get("data-module-args", "{}"))
                            course.set_metadata(dma)
                        except Exception: pass
                    if not course.course_id:
                        course.course_id = self._extract_course_id(soup)
                    if course.course_id:
                        if course.coupon_code:
                            logger.debug(f"  Success: Found ID {course.course_id} and coupon via Playwright")
                        else:
                            logger.debug(f"  Success: Found ID {course.course_id} via Playwright (still no coupon)")
                        return
                    break
                elif resp and resp.status_code == 403:
                    consecutive_403 += 1
                    playwright_cf_blocked = True
                    if consecutive_403 < max_403_retries:
                        logger.warning(f"403 Forbidden on course fetch for {course.title}. Forcing full session re-challenge (attempt {consecutive_403}/{max_403_retries})...")
                        # force_full=True: invalidate cf_clearance and re-challenge.
                        # Plain CSRF rotation can't fix a document-GET 403.
                        if await self._refresh_csrf_stealth(force_full=True):
                            await asyncio.sleep(2)
                            continue
                    logger.error(f"Too many 403 errors ({consecutive_403}) on Playwright course fetch. Giving up.")
                    break
                else:
                    logger.debug(f"Playwright returned {resp.status_code if resp else 'None'}.")
                    break

        # Skip the raw-HTTP fallback when Playwright already hit a CF 403: vanilla
        # httpx has a Python TLS fingerprint and cannot succeed where Chromium
        # just failed.  Retrying here just wastes time and inflates error counts.
        if not course.course_id and not playwright_cf_blocked:
            logger.info(f"Standard: Fetching course ID for {course.title} via HTTP...")
            consecutive_403 = 0
            while consecutive_403 < max_403_retries:
                resp = await self.http.get(url, req_type="document", raise_for_status=False)
                if resp and resp.status_code == 200:
                    soup = bs(resp.content, "lxml")
                    body = soup.find("body")
                    if body:
                        try:
                            dma = json.loads(body.get("data-module-args", "{}"))
                            course.set_metadata(dma)
                        except Exception: pass
                    if not course.course_id:
                        course.course_id = self._extract_course_id(soup)
                    if course.course_id:
                        logger.debug(f"  Success: Found ID {course.course_id} via HTTP")
                        return
                    break
                elif resp and resp.status_code == 403:
                    consecutive_403 += 1
                    if consecutive_403 < max_403_retries:
                        logger.warning(f"403 Forbidden on standard course fetch for {course.title}. Refreshing session (attempt {consecutive_403}/{max_403_retries})...")
                        if await self._refresh_csrf_stealth(force_full=True):
                            await asyncio.sleep(1)
                            continue
                    logger.error(f"Too many 403 errors ({consecutive_403}) on standard course fetch. Giving up.")
                    break
                else:
                    break

        if not course.course_id:
            course.is_valid = False
            if resp and resp.status_code == 200:
                course.error = "Course ID not found"
            else:
                course.error = f"Failed to fetch course page ({resp.status_code if resp else 'No response'})"
            logger.warning(f"Failed to identify course: {course.title}")

    async def check_course(self, course: Course):
        """Check coupon validity with Firecrawl-first, Playwright fallback chain."""
        if course.price is not None:
            return
        
        url = f"{constants.UDEMY_COURSE_LANDING_COMPONENTS_URL}{course.course_id}/me/?components=purchase"
        if course.coupon_code:
            url += f",redeem_coupon&couponCode={course.coupon_code}"

        r = None
        if self.firecrawl_api_key:
            logger.info(f"Stealth: Checking coupon for {course.title} via Firecrawl...")
            fc_data = await self._firecrawl_scrape(url)
            if fc_data and "content" in fc_data:
                try:
                    r = json.loads(fc_data["content"])
                except Exception: pass

        if not r:
            logger.info(f"Stealth: Checking coupon for {course.title} via Playwright...")
            resp = await self._playwright_request(url)
            if resp and resp.status_code == 200:
                r = await self.http.safe_json(resp, "playwright check course")

        if not r:
            course.is_coupon_valid = False
            course.error = "Failed to fetch course price info"
            return

        purchase_data = r.get("purchase", {}).get("data", {})
        amount = purchase_data.get("list_price", {}).get("amount")
        course.price = Decimal(str(amount)) if amount is not None else None

        if course.coupon_code:
            if "redeem_coupon" in r:
                discount_attempts = r["redeem_coupon"].get("discount_attempts", [])
                if discount_attempts:
                    status = discount_attempts[0].get("status")
                    pricing = purchase_data.get("pricing_result", {})
                    discount = pricing.get("discount_percent")
                    
                    if (status == "applied" or status == "unused") and discount == 100:
                        course.is_coupon_valid = True
                    else:
                        course.is_coupon_valid = False
                        if status not in ("applied", "unused"):
                            course.error = f"Coupon status: {status}"
                        elif discount != 100:
                            course.error = f"Coupon only {discount}% off (not 100%)"
                else:
                    course.is_coupon_valid = False
                    course.error = "No discount attempts returned"
            else:
                course.is_coupon_valid = False
                course.error = "Coupon not found in response"
        else:
            course.is_coupon_valid = False
            course.error = "No coupon code provided"

    async def is_already_enrolled(self, course: Course, known_slugs: set = None) -> bool:
        if self.enrolled_courses is None:
            await self.get_enrolled_courses(known_slugs)
        return course.slug in self.enrolled_courses

    def is_course_excluded(self, course: Course, settings: dict):
        return

    async def free_checkout(self, course: Course):
        """Enroll in a free course with Playwright-first stealth fallback."""
        sub_url = f"{constants.UDEMY_COURSE_SUBSCRIBE_URL}?courseId={course.course_id}"
        status_url = f"{constants.UDEMY_SUBSCRIBED_COURSES_URL}{course.course_id}/?fields%5Bcourse%5D=%40default%2Cbuyable_object_type%2Cprimary_subcategory%2Cis_private"
        
        csrf_token = self.http.client.cookies.get("csrftoken") or self.cookie_dict.get("csrf_token", "")
        
        logger.info(f"Stealth: Enrolling in free course {course.title} via Playwright...")
        resp = await self._playwright_request(sub_url, method="POST")
        if resp and resp.status_code == 200:
            check_resp = await self._playwright_request(status_url)
            if check_resp and check_resp.status_code == 200:
                data = await self.http.safe_json(check_resp, "playwright free checkout check")
                course.status = data.get("_class") == "course" if data else False
                if course.status: 
                    logger.debug(f"  Success: Enrolled in {course.title} via Playwright")
                    return

        logger.info(f"Standard: Enrolling in free course {course.title}...")
        headers = {"X-CSRF-Token": csrf_token} if csrf_token else {}
        await self.http.post(sub_url, cookies=self.cookie_dict, headers=headers, req_type="api", log_failures=False)
        
        resp = await self.http.get(status_url, cookies=self.cookie_dict, req_type="api", log_failures=False)
        if resp and resp.status_code == 200:
            data = await self.http.safe_json(resp, "standard free checkout check")
            course.status = data.get("_class") == "course" if data else False
            if course.status:
                return

        logger.info(f"Fallback: Using checkout pipeline for free course {course.title}...")
        course.status = await self.checkout_single(course)

    async def checkout_single(self, course: Course) -> bool:
        """Asynchronously enroll in a single course with a coupon."""
        max_retry_attempts = 2
        attempt_count = 0
        
        for retry_attempt in range(max_retry_attempts):
            attempt_count += 1
            csrf_token = self.http.client.cookies.get("csrftoken") or self.cookie_dict.get("csrf_token", "")
            if not csrf_token:
                 refresh_success = await self._refresh_csrf_stealth()
                 if not refresh_success:
                     logger.error(f"Failed to obtain CSRF token for {course.title}")
                     if retry_attempt >= max_retry_attempts - 1:
                         return False
                     await asyncio.sleep(2)
                     continue
                 csrf_token = self.http.client.cookies.get("csrftoken") or self.cookie_dict.get("csrf_token", "")
                 if not csrf_token:
                     logger.error(f"CSRF token still empty after refresh for {course.title}")
                     if retry_attempt >= max_retry_attempts - 1:
                         return False
                     await asyncio.sleep(2)
                     continue

            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": constants.UDEMY_CHECKOUT_URL,
                "X-CSRF-Token": csrf_token,
            }
            if self.cookie_dict.get("access_token"):
                headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

            result = await self._checkout_one(course, headers)
            if result:
                logger.debug(f"✓ Single-course checkout succeeded for {course.title} (attempt {attempt_count})")
                return True
        
        logger.warning(f"✗ Single-course checkout failed for {course.title} after {attempt_count} attempts")
        return False

    @staticmethod
    def _title_overlap(a: str, b: str) -> float:
        def tokenize(s):
            s = re.sub(r'\b(20\d{2})\b', '', s)
            s = re.sub(r'[^\w\s]', '', s.lower())
            return set(s.split()) - {'the', 'a', 'an', 'and', 'or', 'in', 'of', 'to', 'for'}
        ta, tb = tokenize(a), tokenize(b)
        if not ta or not tb: return 0.0
        return len(ta & tb) / len(ta | tb)

    def _throttle_wait(self, result: dict) -> int:
        detail = result.get("detail", "")
        if "throttled" in str(detail).lower():
            match = re.search(r"(\d+)\s+second", str(detail), re.IGNORECASE)
            return int(match.group(1)) if match else 60
        return 0

    async def _checkout_one(self, course: Course, headers: dict) -> bool:
        """Enroll with coupon via Playwright-first stealth chain (POST required)."""
        payload = {
            "checkout_environment": "Marketplace",
            "checkout_event": "Submit",
            "payment_info": {"method_id": "0", "payment_method": "free-method", "payment_vendor": "Free"},
            "shopping_info": {
                "items": [{
                    "buyable": {"id": str(course.course_id), "type": "course"},
                    "discountInfo": {"code": course.coupon_code},
                    "price": {"amount": 0, "currency": self.currency.upper()},
                }],
                "is_cart": True,
            },
        }
        
        # Increase max attempts significantly due to Cloudflare challenges
        max_attempts = 7  # Increased from 5
        consecutive_403_count = 0
        max_403_consecutive = 4  # Increased from 3 (Cloudflare can cause multiple 403s)
        
        for attempt in range(max_attempts):
            # Try to get CSRF token from multiple sources (prioritize real tokens)
            csrf = (self.http.client.cookies.get("csrftoken") or 
                   self.cookie_dict.get("csrf_token") or 
                   self.cookie_dict.get("_csrf_from_header") or 
                   self.http.client.headers.get("X-CSRFToken") or 
                   self.cookie_dict.get("_csrf_from_html", ""))
            
            # Log token source for debugging (real vs fallback)
            if csrf:
                token_source = "cookie"
                if "_csrf_from_header" in self.cookie_dict and self.cookie_dict.get("_csrf_from_header") == csrf:
                    token_source = "response_header"
                elif "_csrf_from_html" in self.cookie_dict and self.cookie_dict.get("_csrf_from_html") == csrf:
                    token_source = "html"
                elif "_csrf_fallback" in self.cookie_dict and self.cookie_dict.get("_csrf_fallback") == csrf:
                    token_source = "fallback_uuid"
                    logger.warning(f"Using fallback UUID token for {course.title} - session may be invalid")
                logger.debug(f"Using CSRF token from {token_source}: {csrf[:20]}..." if len(csrf) > 20 else f"Using CSRF token from {token_source}")
            else:
                logger.warning("No CSRF token available for checkout")
            
            headers["X-CSRFToken"] = csrf

            logger.info(f"Stealth: Executing checkout for {course.title} via Playwright (attempt {attempt + 1}/{max_attempts})...")
            resp = await self._playwright_request(constants.UDEMY_CHECKOUT_SUBMIT_URL, method="POST", data=payload)
            
            if not resp or resp.status_code != 200:
                logger.info(f"Standard: Falling back to HTTPX checkout for {course.title}...")
                resp = await self.http.post(constants.UDEMY_CHECKOUT_SUBMIT_URL, json=payload, headers=headers, cookies=self.cookie_dict, randomize_headers=True, req_type="xhr", attempts=1, raise_for_status=False)
            
            if not resp:
                continue
            
            if resp.status_code == 403:
                consecutive_403_count += 1
                if consecutive_403_count > max_403_consecutive:
                    logger.error(f"Too many 403 errors ({consecutive_403_count}) for {course.title}. Giving up.")
                    return False
                
                logger.warning(f"403 Forbidden on checkout for {course.title}. Refreshing session (attempt {consecutive_403_count}/{max_403_consecutive})...")
                
                # Implement improved exponential backoff with jitter
                base_backoff = min(2 ** consecutive_403_count, 16)  # 2, 4, 8, 16 seconds (capped at 16)
                jitter = random.uniform(0.5, 2.0)
                backoff_delay = base_backoff + jitter
                logger.debug(f"Waiting {backoff_delay:.1f}s before session refresh (base: {base_backoff}s, jitter: {jitter:.1f}s)...")
                await asyncio.sleep(backoff_delay)
                
                # On repeated 403 errors, suggest using Firecrawl if available
                if consecutive_403_count >= 2 and self.firecrawl_api_key:
                    logger.info(f"Persistent 403 errors detected. Consider using Firecrawl API for course fetch/checkout operations.")
                
                refresh_success = await self._refresh_csrf_stealth()
                if not refresh_success:
                    logger.error(f"Failed to refresh CSRF token for {course.title}. Session may be invalid.")
                    if consecutive_403_count >= max_403_consecutive:
                        return False
                else:
                    # Extra wait after successful refresh to ensure cookies are synced
                    await asyncio.sleep(3)
                
                continue

            consecutive_403_count = 0
            result = await self.http.safe_json(resp, "checkout one")
            if result and result.get("status") == "succeeded":
                self.amount_saved_c += Decimal(str(course.price or 0))
                self.successfully_enrolled_c += 1
                if self.enrolled_courses is not None:
                    self.enrolled_courses[course.slug] = datetime.now(UTC).isoformat()
                return True
            
            wait = self._throttle_wait(result or {})
            if wait:
                logger.info(f"Throttled. Waiting {wait} seconds before retry...")
                await asyncio.sleep(wait)
                continue
            
            logger.warning(f"Checkout failed with response status {resp.status_code}. Giving up.")
            break
        return False

    async def bulk_checkout(self, courses: List[Course]) -> Dict[Course, str]:
        """Asynchronously enroll in a batch of courses with stealth priority."""
        outcomes: Dict[Course, str] = {c: "failed" for c in courses}
        if not courses:
            return outcomes
        
        # Monitoring metrics
        metrics = {
            "total_attempts": 0,
            "successful_403_recoveries": 0,
            "failed_checkouts": 0,
            "session_blocks": 0,
            "total_delay_time": 0.0,
            "start_time": asyncio.get_event_loop().time(),
        }
        
        remaining = list(courses)
        max_bulk_attempts = len(courses) + 2
        consecutive_403_count = 0
        max_403_consecutive = 3
        
        for attempt in range(max_bulk_attempts):
            if not remaining:
                break
            
            metrics["total_attempts"] += 1
            
            if attempt > 0:
                # Improved exponential backoff with jitter
                # Start at 2s, double each time: 2s, 4s, 8s, 16s (capped)
                base_delay = min(2 ** (attempt), 16)  # Capped at 16 seconds
                # Add extra delay if we've had 403s (adaptive multiplier)
                if consecutive_403_count > 0:
                    adaptive_multiplier = 1.0 + (consecutive_403_count * 0.4)  # 1.4x, 1.8x, 2.2x...
                    base_delay *= adaptive_multiplier
                
                jitter = random.uniform(0.5, 2.0)
                backoff_delay = min(base_delay + jitter, 20)  # Cap final delay at 20 seconds
                metrics["total_delay_time"] += backoff_delay
                
                logger.info(f"Waiting {backoff_delay:.1f}s before bulk checkout retry "
                           f"(attempt {attempt + 1}/{max_bulk_attempts}, "
                           f"403_count={consecutive_403_count}/{max_403_consecutive}, "
                           f"base={base_delay:.1f}s, jitter={jitter:.1f}s)...")
                await asyncio.sleep(backoff_delay)

            csrf_token = (self.http.client.cookies.get("csrftoken") or 
                         self.cookie_dict.get("csrf_token") or 
                         self.http.client.headers.get("X-CSRFToken") or 
                         self.cookie_dict.get("_csrf_from_html", ""))
            if not csrf_token:
                 logger.info(f"No CSRF token for bulk checkout. Refreshing...")
                 refresh_success = await self._refresh_csrf_stealth()
                 if not refresh_success:
                     logger.error(f"Failed to refresh CSRF token for bulk checkout")
                     consecutive_403_count += 1
                     if consecutive_403_count >= max_403_consecutive:
                         logger.error(f"Too many consecutive refresh failures ({consecutive_403_count}). Giving up bulk checkout.")
                         metrics["session_blocks"] += 1
                         break
                     continue
                 csrf_token = (self.http.client.cookies.get("csrftoken") or 
                              self.cookie_dict.get("csrf_token") or 
                              self.http.client.headers.get("X-CSRFToken") or 
                              self.cookie_dict.get("_csrf_from_html", ""))
                 if not csrf_token:
                     logger.error("CSRF token still empty after refresh")
                     consecutive_403_count += 1
                     if consecutive_403_count >= max_403_consecutive:
                         logger.error(f"Too many consecutive CSRF failures. Giving up bulk checkout.")
                         metrics["session_blocks"] += 1
                         break
                     continue

            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.udemy.com/payment/checkout/",
                "X-CSRF-Token": csrf_token,
            }
            if self.cookie_dict.get("access_token"):
                headers["Authorization"] = f"Bearer {self.cookie_dict['access_token']}"

            items = [{
                "buyable": {"id": str(c.course_id), "type": "course"},
                "discountInfo": {"code": c.coupon_code},
                "price": {"amount": 0, "currency": self.currency.upper()},
            } for c in remaining]
            
            payload = {
                "checkout_environment": "Marketplace",
                "checkout_event": "Submit",
                "payment_info": {"method_id": "0", "payment_method": "free-method", "payment_vendor": "Free"},
                "shopping_info": {"items": items, "is_cart": True},
            }
            
            logger.info(f"Stealth: Executing bulk checkout for {len(remaining)} courses via Playwright (attempt {attempt + 1}/{max_bulk_attempts})...")
            resp = await self._playwright_request(constants.UDEMY_CHECKOUT_SUBMIT_URL, method="POST", data=payload)
            
            if not resp or resp.status_code != 200:
                logger.info("Standard: Falling back to HTTPX for bulk checkout...")
                resp = await self.http.post(constants.UDEMY_CHECKOUT_SUBMIT_URL, json=payload, headers=headers, cookies=self.cookie_dict, randomize_headers=True, req_type="xhr", attempts=1, raise_for_status=False)
            
            if not resp:
                logger.warning(f"No response from bulk checkout attempt {attempt + 1}")
                continue
                
            if resp.status_code == 403:
                consecutive_403_count += 1
                self.session_recovery_state["consecutive_403_errors"] += 1
                self.session_recovery_state["last_error_time"] = datetime.now(UTC)
                
                if consecutive_403_count > max_403_consecutive:
                    logger.error(f"Too many 403 errors ({consecutive_403_count}) on bulk checkout. Session may be blocked. Giving up.")
                    metrics["session_blocks"] += 1
                    logger.error(f"Session recovery state: {self.session_recovery_state}")
                    logger.info("Recommendation: Wait 30-60 seconds and retry, or switch to single-course mode")
                    break
                
                logger.warning(f"Bulk checkout hit 403 Forbidden (attempt {consecutive_403_count}/{max_403_consecutive}). "
                             f"Refreshing session... [Total attempts: {metrics['total_attempts']}]")
                
                # Implement improved exponential backoff before refresh
                base_backoff = min(2 ** consecutive_403_count, 16)  # 2, 4, 8, 16 seconds
                jitter = random.uniform(0.5, 2.0)
                backoff_delay = base_backoff + jitter
                metrics["total_delay_time"] += backoff_delay
                logger.debug(f"Waiting {backoff_delay:.1f}s before session refresh (base: {base_backoff}s, jitter: {jitter:.1f}s)...")
                await asyncio.sleep(backoff_delay)
                
                refresh_success = await self._refresh_csrf_stealth()
                if refresh_success:
                    metrics["successful_403_recoveries"] += 1
                    logger.info(f"✓ Successfully recovered from 403 (recovery #{metrics['successful_403_recoveries']})")
                    # Extra wait after refresh to ensure session is ready
                    await asyncio.sleep(2)
                else:
                    logger.error("Failed to refresh CSRF after 403 - session may be blocked")
                    logger.info("Current session recovery state: " + str(self.session_recovery_state))
                    metrics["failed_checkouts"] += 1
                continue

            consecutive_403_count = 0
            result = await self.http.safe_json(resp, "bulk checkout")
            
            if result and result.get("status") == "succeeded":
                for c in remaining:
                    self.amount_saved_c += Decimal(str(c.price or 0))
                    self.successfully_enrolled_c += 1
                    if self.enrolled_courses is not None:
                        self.enrolled_courses[c.slug] = datetime.now(UTC).isoformat()
                    outcomes[c] = "enrolled"
                
                elapsed = asyncio.get_event_loop().time() - metrics["start_time"]
                logger.info(f"✓ Bulk checkout succeeded for {len(remaining)} courses "
                           f"[Attempts: {metrics['total_attempts']}, Time: {elapsed:.1f}s, "
                           f"403 Recoveries: {metrics['successful_403_recoveries']}]")
                break
            
            msg = result.get("message", "") if result else ""
            developer_message = (result or {}).get("developer_message", "")
            if "item_already_subscribed" in str(developer_message):
                quoted = re.search(r'"([^"]+)"', msg)
                error_title = quoted.group(1) if quoted else ""
                
                offender = None
                if error_title:
                    best_score, best_course = 0.0, None
                    for c in remaining:
                        score = self._title_overlap(c.title, error_title)
                        if score > best_score:
                            best_score, best_course = score, c
                    if best_score >= 0.4:
                        offender = best_course
                
                if offender:
                    logger.info(f"Course {offender.title} already enrolled. Removing from batch...")
                    remaining.remove(offender)
                    self.already_enrolled_c += 1
                    outcomes[offender] = "already_enrolled"
                    continue
                
                logger.info(f"Conflict detected but couldn't identify specific course. Falling back to single enrollments...")
                for c in remaining:
                    success = await self.checkout_single(c)
                    outcomes[c] = "enrolled" if success else "failed"
                break

            wait = self._throttle_wait(result or {})
            if wait:
                logger.info(f"Throttled. Waiting {wait} seconds before retry...")
                await asyncio.sleep(wait)
                continue
            
            logger.warning(f"Bulk checkout failed (attempt {attempt + 1}). Response: {result}")
            break
        
        # Log final metrics
        elapsed = asyncio.get_event_loop().time() - metrics["start_time"]
        success_rate = (len([o for o in outcomes.values() if o == "enrolled"]) / len(courses) * 100) if courses else 0
        
        logger.info(f"📊 Bulk Checkout Metrics: "
                   f"Attempts={metrics['total_attempts']}, "
                   f"403_Recoveries={metrics['successful_403_recoveries']}, "
                   f"Session_Blocks={metrics['session_blocks']}, "
                   f"Total_Delay={metrics['total_delay_time']:.1f}s, "
                   f"Success_Rate={success_rate:.1f}%, "
                   f"Duration={elapsed:.1f}s")
        
        return outcomes
