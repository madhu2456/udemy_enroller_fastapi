"""Application constants and URLs."""

import asyncio

UDEMY_BASE_URL = "https://www.udemy.com"
UDEMY_API_BASE = f"{UDEMY_BASE_URL}/api-2.0"

# Auth URLs
UDEMY_LOGIN_POPUP_URL = (
    f"{UDEMY_BASE_URL}/join/login-popup/?passwordredirect=True&response_type=json"
)
UDEMY_SIGNUP_POPUP_URL = f"{UDEMY_BASE_URL}/join/signup-popup/?locale=en_US&response_type=html&next=https%3A%2F%2Fwww.udemy.com%2Flogout%2F"

# API Endpoints
UDEMY_CONTEXT_URL = f"{UDEMY_API_BASE}/contexts/me/?header=True"
UDEMY_CART_URL = f"{UDEMY_API_BASE}/shopping-carts/me/"
UDEMY_SUBSCRIBED_COURSES_URL = f"{UDEMY_API_BASE}/users/me/subscribed-courses/"
UDEMY_COURSE_LANDING_COMPONENTS_URL = f"{UDEMY_API_BASE}/course-landing-components/"
UDEMY_CHECKOUT_URL = f"{UDEMY_BASE_URL}/payment/checkout/"
UDEMY_CHECKOUT_SUBMIT_URL = f"{UDEMY_BASE_URL}/payment/checkout-submit/"
UDEMY_COURSE_SUBSCRIBE_URL = f"{UDEMY_BASE_URL}/course/subscribe/"

# Common Headers
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

_shutdown_event: asyncio.Event | None = None


def get_shutdown_event() -> asyncio.Event:
    try:
        loop = asyncio.get_running_loop()
        if not hasattr(loop, "_shutdown_event"):
            loop._shutdown_event = asyncio.Event()
        return loop._shutdown_event
    except RuntimeError:
        global _shutdown_event
        if _shutdown_event is None:
            _shutdown_event = asyncio.Event()
        return _shutdown_event


def reset_shutdown_event() -> None:
    global _shutdown_event
    _shutdown_event = None
    try:
        loop = asyncio.get_running_loop()
        if hasattr(loop, "_shutdown_event"):
            delattr(loop, "_shutdown_event")
    except RuntimeError:
        pass


class _ShutdownEventProxy:
    """Transparent proxy delegating dynamically to loop-bound get_shutdown_event()."""

    def __getattr__(self, name: str):
        return getattr(get_shutdown_event(), name)

    def is_set(self) -> bool:
        return get_shutdown_event().is_set()

    def set(self) -> None:
        get_shutdown_event().set()

    def clear(self) -> None:
        get_shutdown_event().clear()

    async def wait(self) -> bool:
        return await get_shutdown_event().wait()

    def __repr__(self) -> str:
        return repr(get_shutdown_event())


shutdown_event = _ShutdownEventProxy()

# Known false-positive course IDs from Udemy (not actual courses)
BLACKLIST_IDS = {"562413829"}

# FM-036 / W3-02: Unknown-price sentinel — fail-closed to 9999.0 so that
# courses with price=None are never treated as free (is_valid_free requires
# price is not None AND price == 0). Shared constant for bridge, enroll, check.
FM036_PRICE_UNKNOWN: float = 9999.0
