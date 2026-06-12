import asyncio
import nodriver

async def main():
    browser = await nodriver.start(headless=True)
    page = await browser.get('https://coursecouponclub.com/feed/')
    await asyncio.sleep(5)
    content = await page.get_content()
    print('cloudflare' in content.lower() or 'just a moment' in content.lower())
    browser.stop()

if __name__ == '__main__':
    asyncio.run(main())
