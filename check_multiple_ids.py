import asyncio
import os
import sys
sys.path.append(os.getcwd())
from app.services.playwright_service import PlaywrightService
from bs4 import BeautifulSoup as bs

async def check_courses():
    urls = [
        "https://www.udemy.com/course/professional-certificate-in-project-management/",
        "https://www.udemy.com/course/sap-mm-training-course/",
        "https://www.udemy.com/course/databricks-certified-data-engineer-professional/"
    ]
    
    async with PlaywrightService() as pw:
        for url in urls:
            print(f"Checking: {url}")
            content = await pw.get_page_content(url)
            if content:
                soup = bs(content, "lxml")
                body = soup.find("body")
                cid = body.get("data-clp-course-id") if body else "No Body"
                print(f"  data-clp-course-id: {cid}")
                
                # Check for 562413829 specifically
                if "562413829" in content:
                    print("  FOUND 562413829 in HTML content!")
                else:
                    print("  562413829 NOT in HTML content.")
            else:
                print("  Failed to get content")

if __name__ == "__main__":
    asyncio.run(check_courses())
