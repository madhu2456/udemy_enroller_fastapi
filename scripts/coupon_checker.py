import asyncio
import logging
import sys
import os
import random
from datetime import datetime, UTC

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import SessionLocal, EnrolledCourse
from app.services.http_client import AsyncHTTPClient
from config.settings import get_settings
from sqlalchemy import or_, desc

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def get_course_id_and_check(http, course):
    """Fetch the course page to find the ID and validate the coupon."""
    url = course.url
    coupon = course.coupon_code
    
    if not coupon:
        return
        
    try:
        # First, we need the course_id.
        if not course.course_id:
            # We can get course_id from the course page HTML
            resp = await http.get(url, use_cloudscraper=True)
            if not resp or not resp.text:
                logger.warning(f"Failed to load course page for {url}")
                return
            
            # Simple regex or string search for course id
            import re
            match = re.search(r'data-course-id="(\d+)"', resp.text)
            if not match:
                match = re.search(r'course_id=(\d+)', resp.text)
            if match:
                course.course_id = match.group(1)
            else:
                logger.warning(f"Could not find course_id for {url}")
                return

        # Now check the pricing API unauthenticated.
        # DO NOT use any authorization headers to avoid WAF flags.
        api_url = f"https://www.udemy.com/api-2.0/course-landing-components/{course.course_id}/me/?components=purchase,redeem_coupon&discountCode={coupon}"
        
        raw_resp = await http.get(api_url, use_cloudscraper=True)
        resp = await http.safe_json(raw_resp)
        if not resp:
            logger.warning(f"Failed to get pricing data for {url}")
            return
            
        purchase = resp.get("purchase") or resp.get("cacheable_purchase")
        if not purchase:
            logger.warning(f"No purchase data returned for {url}")
            return
            
        purchase_data = purchase.get("data", {})
        pricing_result = purchase_data.get("pricing_result", {})
        
        # Track list price for "amount saved" stats
        lp = purchase_data.get("list_price", {}).get("amount") or 0
        
        price_obj = pricing_result.get("price")
        if price_obj is None:
            # If there's no price object, only trust explicit is_free flag
            is_free_result = pricing_result.get("is_free", False)
            final_price = 0 if is_free_result else 9999.0
        else:
            final_price = price_obj.get("amount") or 0
            is_free_result = pricing_result.get("is_free", False) or final_price == 0
        
        course.is_coupon_valid = is_free_result
            
        course.price = float(lp) if lp else course.price
        status_text = "VALID" if is_free_result else "EXPIRED"
        logger.info(f"[{status_text}] {course.title} - Price: {final_price}")
        
    except Exception as e:
        logger.error(f"Error checking {url}: {e}")

async def main():
    logger.info("Starting Coupon Checker...")
    db = SessionLocal()
    settings = get_settings()
    
    try:
        courses = db.query(EnrolledCourse).filter(
            EnrolledCourse.coupon_code.isnot(None)
        ).order_by(desc(EnrolledCourse.enrolled_at)).limit(1000).all()
        
        logger.info(f"Found {len(courses)} recent courses to check (limited to latest 1000).")
        
        # Setup proxy if available in settings to avoid IP blocks
        proxy_url = None
        if settings.PROXIES:
            proxies = [p.strip() for p in settings.PROXIES.split(',') if p.strip()]
            if proxies:
                proxy_url = random.choice(proxies)
                logger.info(f"Using proxy to avoid IP blocks.")
                
        http = AsyncHTTPClient(proxy=proxy_url)
        
        # Process in small batches
        batch_size = 5
        for i in range(0, len(courses), batch_size):
            batch = courses[i:i+batch_size]
            tasks = [get_course_id_and_check(http, c) for c in batch]
            await asyncio.gather(*tasks)
            
            for c in batch:
                c.last_checked_at = datetime.now(UTC).replace(tzinfo=None)
            
            db.commit()
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(courses) + batch_size - 1)//batch_size}")
            
            # Conservative rate limiting sleep to protect IP
            await asyncio.sleep(3)
            
    finally:
        db.close()
        logger.info("Coupon Check Completed.")

if __name__ == "__main__":
    asyncio.run(main())
