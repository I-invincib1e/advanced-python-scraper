import os
import asyncio
import time
import re
import random
import json
import yaml
from typing import List, Tuple, Optional, Dict, Any
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass
from tqdm.asyncio import tqdm

# Optional Playwright support
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None

@dataclass
class ScrapeMetrics:
    total_pages: int = 0
    successful_pages: int = 0
    failed_pages: int = 0
    total_time: float = 0.0
    avg_time_per_page: float = 0.0
    total_size_mb: float = 0.0

class BookScraper:
    def __init__(self, base_url: str, output_dir: str = None, max_concurrent: int = 10, config_file: str = None, backend: str = 'aiohttp'):
        self.base_url = base_url
        self.max_concurrent = max_concurrent
        self.backend = backend.lower()
        self.metrics = ScrapeMetrics()
        self.session: Optional[aiohttp.ClientSession] = None

        # Playwright components (if using playwright backend)
        self.playwright = None
        self.browser = None
        self.context = None

        # Load configuration
        self.config = self._load_config(config_file)

        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
        ]

        # Rate limiting
        self.request_delay = self.config.get('rate_limiting', {}).get('delay', 0.1)
        self.max_retries = self.config.get('retry', {}).get('max_attempts', 3)

        # Create organized directory structure
        if output_dir is None:
            website_name = self._extract_website_name(base_url)
            self.output_dir = os.path.join("scrape", website_name)
        else:
            self.output_dir = output_dir

        # HTML template for clean formatting
        self.html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body {{ font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; line-height:1.55; padding:1.25rem; max-width:900px; margin:auto; }}
pre,code {{ font-family: ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace; }}
pre {{ overflow-x:auto; background:#fafafa; border:1px solid #eee; padding:0.75rem; border-radius:8px; }}
img {{ max-width:100%; height:auto; }}
hr {{ border:none; border-top:1px solid #e5e5e5; margin:2rem 0; }}
h1,h2,h3 {{ line-height:1.25; }}
a {{ color:#0a7; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
</style>
</head>
<body>
<h1>{title}</h1>
<hr />
{inner_html}
</body>
</html>"""

    def _extract_website_name(self, url: str) -> str:
        """Extract website name from URL for directory structure"""
        parsed = urlparse(url)
        domain = parsed.netloc

        # Remove www. prefix and get main domain
        domain = re.sub(r'^www\.', '', domain)

        # Replace dots and special chars with underscores
        website_name = re.sub(r'[^\w\-]', '_', domain)

        return website_name

    def _load_config(self, config_file: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from JSON or YAML file"""
        default_config = {
            'rate_limiting': {
                'delay': 0.1,
                'enabled': True
            },
            'retry': {
                'max_attempts': 3,
                'backoff_factor': 0.5
            },
            'user_agent_rotation': {
                'enabled': True
            },
            'concurrency': {
                'max_concurrent': 10
            }
        }

        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                        file_config = yaml.safe_load(f)
                    else:
                        file_config = json.load(f)

                # Merge with defaults
                def merge_dicts(default: Dict, override: Dict) -> Dict:
                    result = default.copy()
                    for key, value in override.items():
                        if isinstance(value, dict) and key in result:
                            result[key] = merge_dicts(result[key], value)
                        else:
                            result[key] = value
                    return result

                return merge_dicts(default_config, file_config)
            except Exception as e:
                print(f"Error loading config file {config_file}: {e}")
                print("Using default configuration...")

        return default_config

    def _format_html_content(self, title: str, original_html: str) -> str:
        """Apply clean HTML template to content"""
        try:
            soup = BeautifulSoup(original_html, 'html.parser')

            # Extract title
            if not title or title == 'Home':
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()
                else:
                    title = "Scraped Page"

            # Extract main content (try common selectors)
            content_selectors = ['main', 'article', '.content', '#content', 'body']
            inner_html = ""

            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    inner_html = str(content_elem)
                    break

            # Fallback to body content
            if not inner_html:
                body = soup.find('body')
                if body:
                    inner_html = str(body)
                else:
                    inner_html = original_html

            return self.html_template.format(title=title, inner_html=inner_html)

        except Exception as e:
            print(f"Error formatting HTML: {e}")
            return original_html

    async def __aenter__(self):
        if self.backend == 'playwright':
            if not PLAYWRIGHT_AVAILABLE:
                raise ImportError("Playwright not installed. Install with: pip install playwright && playwright install")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context()
        else:
            self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.backend == 'playwright':
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        else:
            if self.session:
                await self.session.close()

    async def scrape_single_page(self, url: str) -> Optional[str]:
        """Scrape a single page with retry mechanism, user agent rotation, and rate limiting"""
        for attempt in range(self.max_retries):
            try:
                # Rate limiting delay
                if self.config.get('rate_limiting', {}).get('enabled', True):
                    await asyncio.sleep(self.request_delay)

                if self.backend == 'playwright':
                    # Playwright backend
                    page = await self.context.new_page()

                    # Set user agent
                    if self.config.get('user_agent_rotation', {}).get('enabled', True):
                        await page.set_extra_http_headers({
                            'User-Agent': random.choice(self.user_agents)
                        })

                    await page.goto(url, wait_until='networkidle')
                    content = await page.content()
                    await page.close()
                    return content

                else:
                    # aiohttp backend (default)
                    headers = {}
                    if self.config.get('user_agent_rotation', {}).get('enabled', True):
                        headers['User-Agent'] = random.choice(self.user_agents)

                    async with self.session.get(url, headers=headers) as response:
                        response.raise_for_status()
                        return await response.text()

            except Exception as e:
                if attempt < self.max_retries - 1:
                    backoff_factor = self.config.get('retry', {}).get('backoff_factor', 0.5)
                    delay = backoff_factor * (2 ** attempt)
                    print(f"Attempt {attempt + 1} failed for {url}: {e}")
                    print(f"Retrying in {delay:.1f} seconds...")
                    await asyncio.sleep(delay)
                else:
                    print(f"Final attempt failed for {url}: {e}")
                    return None

        return None

    def extract_chapter_links(self, html_content: str) -> List[Tuple[str, str]]:
        """Extract chapter links from HTML content"""
        soup = BeautifulSoup(html_content, 'html.parser')
        chapter_links = []

        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('/bigbookpython/') and href.endswith('.html'):
                full_url = urljoin(self.base_url, href)
                title = link.text.strip()
                chapter_links.append((title, full_url))

        return chapter_links

    async def scrape_page_worker(self, title: str, url: str, semaphore: asyncio.Semaphore) -> bool:
        """Worker function to scrape a single page with semaphore control"""
        async with semaphore:
            start_time = time.time()
            print(f"Scraping: {title} - {url}")

            content = await self.scrape_single_page(url)
            if content:
                # Apply clean HTML formatting
                formatted_content = self._format_html_content(title, content)

                # Save the HTML content
                filename = url.split('/')[-1] or 'index.html'

                # Clean filename - remove URL fragments and ensure proper extension
                if '#' in filename:
                    filename = filename.split('#')[0]

                # Ensure .html extension
                if not filename.endswith(('.html', '.htm')):
                    filename += '.html'

                # Clean any remaining invalid characters
                filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

                filepath = os.path.join(self.output_dir, filename)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(formatted_content)

                self.metrics.successful_pages += 1
                self.metrics.total_size_mb += len(formatted_content) / (1024 * 1024)
                page_time = time.time() - start_time
                self.metrics.total_time += page_time
                print(".2f")
                return True
            else:
                self.metrics.failed_pages += 1
                return False

    async def scrape_multiple_pages(self, pages: List[Tuple[str, str]]) -> None:
        """Scrape multiple pages concurrently with progress bar"""
        os.makedirs(self.output_dir, exist_ok=True)

        self.metrics.total_pages = len(pages)
        semaphore = asyncio.Semaphore(self.max_concurrent)

        print(f"\n🚀 Starting scrape of {len(pages)} pages...")

        # Create progress-aware tasks
        async def progress_wrapper(title: str, url: str, pbar: tqdm) -> bool:
            result = await self.scrape_page_worker(title, url, semaphore)
            pbar.update(1)
            return result

        with tqdm(total=len(pages), desc="Scraping", unit="page") as pbar:
            tasks = [progress_wrapper(title, url, pbar) for title, url in pages]
            await asyncio.gather(*tasks)

        # Calculate final metrics
        if self.metrics.successful_pages > 0:
            self.metrics.avg_time_per_page = self.metrics.total_time / self.metrics.successful_pages

    def print_metrics(self):
        """Print scraping metrics"""
        print("\n" + "="*50)
        print("SCRAPING METRICS")
        print("="*50)
        print(f"Total pages processed: {self.metrics.total_pages}")
        print(f"Successful pages: {self.metrics.successful_pages}")
        print(f"Failed pages: {self.metrics.failed_pages}")
        print(".2f")
        print(".2f")
        print(".2f")
        print(".2f")
        print("="*50)

async def main():
    print("🚀 Advanced Python Web Scraper")
    print("=" * 50)

    # Get base URL from user
    base_url = input("Enter the website URL to scrape: ").strip()
    if not base_url:
        print("❌ No URL provided. Exiting...")
        return

    # Ensure URL has protocol
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'https://' + base_url

    print(f"📍 Target URL: {base_url}")

    # Backend selection
    print("\n🔧 Available backends:")
    print("1. aiohttp (default) - Fast for static sites")
    print("2. playwright - Recommended for JavaScript sites")
    backend_choice = input("Choose backend (1 or 2, press Enter for default): ").strip()

    backend = 'aiohttp'  # default
    if backend_choice == '2':
        backend = 'playwright'
        if not PLAYWRIGHT_AVAILABLE:
            print("❌ Playwright not installed. Install with: pip install playwright && playwright install")
            print("Falling back to aiohttp...")
            backend = 'aiohttp'

    print(f"✅ Using backend: {backend}")

    # Auto-generate output directory from site name
    async with BookScraper(base_url, backend=backend) as scraper:
        print(f"📁 Output directory: {scraper.output_dir}")

        # Option 1: Scrape single page
        single_page = input("\n🔗 Enter a single page URL to scrape (or press Enter to scrape homepage): ").strip()
        if single_page:
            if not single_page.startswith(('http://', 'https://')):
                single_page = base_url.rstrip('/') + '/' + single_page.lstrip('/')

            print(f"📄 Scraping single page: {single_page}")
            content = await scraper.scrape_single_page(single_page)
            if content:
                formatted_content = scraper._format_html_content("Single Page", content)
                filename = single_page.split('/')[-1] or 'single_page.html'
                filepath = os.path.join(scraper.output_dir, filename)
                os.makedirs(scraper.output_dir, exist_ok=True)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(formatted_content)
                print(f"✅ Saved to: {filepath}")
            else:
                print("❌ Failed to scrape the page")
            return

        # Option 2: Scrape from homepage with ALL links
        print("🏠 Scraping homepage to find all available content...")

        home_content = await scraper.scrape_single_page(base_url)
        if not home_content:
            print("❌ Failed to scrape homepage")
            return

        print("🔍 Analyzing homepage for links...")

        # Extract ALL links from the page
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(home_content, 'html.parser')
        all_links = soup.find_all('a', href=True)

        # Filter for substantial content links
        content_links = []
        for link in all_links:
            href = link['href']
            text = link.text.strip()

            # Skip if href is empty or just '#'
            if not href or href == '#':
                continue

            # Convert relative URLs to absolute
            if not href.startswith(('http://', 'https://')):
                href = urljoin(base_url, href)

            # Skip external links (different domain)
            if urlparse(href).netloc != urlparse(base_url).netloc:
                continue

            # Skip very short text or navigation links
            if len(text) < 3:
                continue

            # Skip common non-content links
            skip_patterns = ['home', 'index', 'contact', 'about', 'privacy', 'terms']
            if any(pattern in text.lower() for pattern in skip_patterns):
                continue

            content_links.append((text, href))

        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for text, href in content_links:
            if href not in seen:
                seen.add(href)
                unique_links.append((text, href))

        print(f"📚 Found {len(unique_links)} content pages to scrape")

        if not unique_links:
            print("❌ No content links found on the homepage")
            return

        # Show sample of what will be scraped
        print("\n📖 Sample of content to be scraped:")
        for i, (title, url) in enumerate(unique_links[:5], 1):
            print(f"{i}. {title[:50]}...")
        if len(unique_links) > 5:
            print(f"... and {len(unique_links) - 5} more pages")

        # Confirm scraping ALL pages
        print(f"\n⚠️  This will scrape ALL {len(unique_links)} pages found on the site")
        confirm = input("Proceed with scraping ALL pages? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Scraping cancelled")
            return

        print(f"\n🚀 Starting comprehensive scrape of {len(unique_links)} pages...")
        print("This may take some time depending on the site size and your connection...")

        start_time = time.time()
        await scraper.scrape_multiple_pages(unique_links)
        scraper.print_metrics()

        print(f"\n🎉 Scraping completed successfully!")
        print(f"📁 All files saved in: {scraper.output_dir}")
        print(f"⏱️  Total time: {time.time() - start_time:.1f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
