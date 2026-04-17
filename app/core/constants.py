"""Application constants and URLs."""

UDEMY_BASE_URL = "https://www.udemy.com"
UDEMY_API_BASE = f"{UDEMY_BASE_URL}/api-2.0"

# Auth URLs
UDEMY_LOGIN_POPUP_URL = f"{UDEMY_BASE_URL}/join/login-popup/?passwordredirect=True&response_type=json"
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
DEFAULT_USER_AGENT = "okhttp/4.9.2 UdemyAndroid 8.9.2(499) (phone)"

import asyncio
shutdown_event = asyncio.Event()
