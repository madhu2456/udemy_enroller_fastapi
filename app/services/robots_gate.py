"""robots.txt compliance gate for coupon-aggregator scraping (F252).

Policy (documented): before the first fetch against a target host, fetch and
cache its robots.txt (per-host cache, 24 h TTL) and honor Disallow rules for
the user-agent family used by the scraper.

- **Fail-open by design:** if the robots.txt fetch fails, times out, returns a
  5xx/non-200, or loops redirects, the gate ALLOWS the fetch. A robots outage
  must never take every coupon source offline (availability > strictness);
  the tradeoff is documented here and in docs/ops/scraping-robots.md.
- **No redirect loops:** the robots.txt fetch follows at most
  ROBOTS_MAX_REDIRECTS redirects; httpx raises TooManyRedirects beyond that,
  which the gate treats as fail-open (allowed) with a warning.
- Detail-page fetches run only after a listing fetch succeeded on the same
  host, so a disallowed host yields no data without gating every request.
"""

import time
from typing import Optional
from urllib import robotparser
from urllib.parse import urlparse

from loguru import logger

# User-agent family token used for robots.txt matching. The HTTP client
# randomizes between Chrome desktop UA strings; robotparser matches on
# whitespace-split tokens, so this family token is the honest match key.
ROBOTS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Per-host robots.txt cache TTL (seconds). Coupon aggregator robots rules
# change rarely; 24 h balances freshness against extra fetches.
ROBOTS_CACHE_TTL_SECONDS = 24 * 60 * 60

# Redirect cap for the robots.txt fetch itself (no redirect loops).
ROBOTS_MAX_REDIRECTS = 3


class RobotsGate:
    """Per-host robots.txt cache + Disallow enforcement (F252)."""

    def __init__(self, http, user_agent: str = ROBOTS_USER_AGENT):
        self.http = http
        self.user_agent = user_agent
        # host -> (monotonic fetch time, parser | None). None = fail-open
        # (robots.txt unavailable) and behaves as "allow everything".
        self._cache: dict[str, tuple[float, Optional[robotparser.RobotFileParser]]] = {}

    @staticmethod
    def _host(url: str) -> Optional[str]:
        parsed = urlparse(url)
        return parsed.netloc.lower() if parsed.netloc else None

    async def _fetch_robots(self, host: str) -> Optional[robotparser.RobotFileParser]:
        """Fetch and parse https://{host}/robots.txt; None on ANY failure."""
        robots_url = f"https://{host}/robots.txt"
        try:
            resp = await self.http.get(
                robots_url,
                use_cloudscraper=False,
                follow_redirects=True,
                max_redirects=ROBOTS_MAX_REDIRECTS,
                raise_for_status=False,
                log_failures=False,
                timeout=10,
                attempts=1,
            )
        except Exception as exc:
            # Includes httpx TooManyRedirects (redirect loop) and transport
            # errors — fail-open (allow) by design, documented policy.
            logger.warning(
                f"robots.txt fetch failed for {host} — allowing (fail-open, F252): "
                f"{type(exc).__name__}"
            )
            return None
        if resp is None:
            return None
        if resp.status_code != 200:
            logger.warning(
                f"robots.txt for {host} returned HTTP {resp.status_code} — "
                "allowing (fail-open, F252)"
            )
            return None
        parser = robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(resp.text.splitlines())
        return parser

    async def is_allowed(self, url: str) -> bool:
        """True when the target host's robots.txt permits this fetch.

        Fail-open (True) when robots.txt cannot be fetched (see module
        policy). Robots.txt content is cached per host for
        ROBOTS_CACHE_TTL_SECONDS.
        """
        host = self._host(url)
        if not host:
            return True
        now = time.monotonic()
        cached = self._cache.get(host)
        if cached is None or now - cached[0] > ROBOTS_CACHE_TTL_SECONDS:
            parser = await self._fetch_robots(host)
            self._cache[host] = (now, parser)
            cached = self._cache[host]
        parser = cached[1]
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)
