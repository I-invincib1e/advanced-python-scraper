#!/usr/bin/env python3
"""
Test script to verify Playwright integration in both scrapers
"""

import asyncio
import sys

async def test_advanced_scraper():
    """Test the advanced scraper with Playwright"""
    print("🧪 Testing Advanced Scraper with Playwright...")

    try:
        from advanced_scraper import AdvancedBookScraper

        async with AdvancedBookScraper(
            base_url="https://httpbin.org",
            backend="playwright"
        ) as scraper:
            content = await scraper.scrape_single_page("https://httpbin.org/html")
            if content and len(content) > 100:
                print("✅ Advanced Scraper with Playwright: SUCCESS")
                return True
            else:
                print("❌ Advanced Scraper with Playwright: FAILED")
                return False

    except Exception as e:
        print(f"❌ Advanced Scraper with Playwright: ERROR - {e}")
        return False

async def test_original_scraper():
    """Test the original scraper with Playwright"""
    print("🧪 Testing Original Scraper with Playwright...")

    try:
        from scraper import BookScraper

        async with BookScraper(
            base_url="https://httpbin.org",
            backend="playwright"
        ) as scraper:
            content = await scraper.scrape_single_page("https://httpbin.org/html")
            if content and len(content) > 100:
                print("✅ Original Scraper with Playwright: SUCCESS")
                return True
            else:
                print("❌ Original Scraper with Playwright: FAILED")
                return False

    except Exception as e:
        print(f"❌ Original Scraper with Playwright: ERROR - {e}")
        return False

async def test_aiohttp_fallback():
    """Test aiohttp fallback when Playwright not available"""
    print("🧪 Testing aiohttp fallback...")

    try:
        from scraper import BookScraper

        async with BookScraper(
            base_url="https://httpbin.org",
            backend="aiohttp"
        ) as scraper:
            content = await scraper.scrape_single_page("https://httpbin.org/html")
            if content and len(content) > 100:
                print("✅ aiohttp fallback: SUCCESS")
                return True
            else:
                print("❌ aiohttp fallback: FAILED")
                return False

    except Exception as e:
        print(f"❌ aiohttp fallback: ERROR - {e}")
        return False

async def main():
    print("🚀 Playwright Integration Test Suite")
    print("=" * 50)

    # Check if Playwright is available
    try:
        from playwright.async_api import async_playwright
        print("✅ Playwright is installed")
        playwright_available = True
    except ImportError:
        print("⚠️  Playwright not installed - some tests will be skipped")
        playwright_available = False

    results = []

    # Test aiohttp fallback (always available)
    results.append(await test_aiohttp_fallback())

    if playwright_available:
        # Test both scrapers with Playwright
        results.append(await test_advanced_scraper())
        results.append(await test_original_scraper())
    else:
        print("⏭️  Skipping Playwright tests (not installed)")

    print("\n" + "=" * 50)
    print("📊 Test Results:")

    passed = sum(results)
    total = len(results)

    print(f"✅ Passed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! Playwright integration is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the output above.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
