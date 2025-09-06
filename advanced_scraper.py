"""
Advanced Scraper with Multiple Backend Support
Supports: aiohttp, requests-html, playwright, scrapy components
"""

import os
import asyncio
import time
import re
import random
import json
from typing import List, Tuple, Optional, Dict, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse
from tqdm.asyncio import tqdm

# Backend imports (optional)
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from requests_html import AsyncHTMLSession
    REQUESTS_HTML_AVAILABLE = True
except ImportError:
    REQUESTS_HTML_AVAILABLE = False

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

@dataclass
class ScrapeMetrics:
    total_pages: int = 0
    successful_pages: int = 0
    failed_pages: int = 0
    total_time: float = 0.0
    avg_time_per_page: float = 0.0
    total_size_mb: float = 0.0

class ScraperBackend(ABC):
    """Abstract base class for scraping backends"""

    @abstractmethod
    async def __aenter__(self):
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    async def scrape_page(self, url: str, headers: Dict[str, str] = None) -> Optional[str]:
        pass

class AioHttpBackend(ScraperBackend):
    """aiohttp backend - Fast and lightweight"""

    def __init__(self, user_agents: List[str], retry_config: Dict[str, Any]):
        self.user_agents = user_agents
        self.max_retries = retry_config.get('max_attempts', 3)
        self.backoff_factor = retry_config.get('backoff_factor', 0.5)
        self.session = None

    async def __aenter__(self):
        if AIOHTTP_AVAILABLE:
            self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def scrape_page(self, url: str, headers: Dict[str, str] = None) -> Optional[str]:
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp not installed")

        for attempt in range(self.max_retries):
            try:
                # Add user agent rotation
                request_headers = headers or {}
                if self.user_agents:
                    request_headers['User-Agent'] = random.choice(self.user_agents)

                async with self.session.get(url, headers=request_headers) as response:
                    response.raise_for_status()
                    return await response.text()

            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.backoff_factor * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    return None
        return None

class RequestsHtmlBackend(ScraperBackend):
    """requests-html backend - JavaScript rendering support"""

    def __init__(self, user_agents: List[str], retry_config: Dict[str, Any]):
        self.user_agents = user_agents
        self.max_retries = retry_config.get('max_attempts', 3)
        self.session = None

    async def __aenter__(self):
        if REQUESTS_HTML_AVAILABLE:
            self.session = AsyncHTMLSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def scrape_page(self, url: str, headers: Dict[str, str] = None) -> Optional[str]:
        if not REQUESTS_HTML_AVAILABLE:
            raise ImportError("requests-html not installed")

        for attempt in range(self.max_retries):
            try:
                # Add user agent rotation
                request_headers = headers or {}
                if self.user_agents:
                    request_headers['User-Agent'] = random.choice(self.user_agents)

                response = await self.session.get(url, headers=request_headers)
                await response.html.arender()  # Render JavaScript
                return response.html.html

            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    return None
        return None

class PlaywrightBackend(ScraperBackend):
    """Playwright backend - Full browser automation"""

    def __init__(self, user_agents: List[str], retry_config: Dict[str, Any]):
        self.user_agents = user_agents
        self.max_retries = retry_config.get('max_attempts', 3)
        self.playwright = None
        self.browser = None
        self.context = None

    async def __aenter__(self):
        if PLAYWRIGHT_AVAILABLE:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def scrape_page(self, url: str, headers: Dict[str, str] = None) -> Optional[str]:
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("playwright not installed")

        for attempt in range(self.max_retries):
            try:
                page = await self.context.new_page()

                # Set user agent
                if self.user_agents:
                    await page.set_extra_http_headers({
                        'User-Agent': random.choice(self.user_agents)
                    })

                await page.goto(url, wait_until='networkidle')
                content = await page.content()
                await page.close()
                return content

            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    return None
        return None

class AdvancedBookScraper:
    """Advanced scraper with multiple backend support"""

    def __init__(self,
                 base_url: str,
                 backend: str = 'aiohttp',
                 output_dir: str = None,
                 max_concurrent: int = 10,
                 config_file: str = None):

        self.base_url = base_url
        self.backend_name = backend
        self.max_concurrent = max_concurrent
        self.metrics = ScrapeMetrics()

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

        # Initialize backend
        self.backend = self._create_backend()

        # Rate limiting
        self.request_delay = self.config.get('rate_limiting', {}).get('delay', 0.1)

        # Create organized directory structure
        if output_dir is None:
            website_name = self._extract_website_name(base_url)
            self.output_dir = os.path.join("scrape", website_name)
        else:
            self.output_dir = output_dir

        # Enhanced content selectors (learned from simple scraper)
        self.content_selectors = [
            "article", "main", ".entry-content", "#content",
            ".post-content", ".article-content", ".content",
            "#main", ".main-content", "body"
        ]

        # Unwanted elements to remove
        self.unwanted_selectors = [
            "nav", "header", "footer", "script", "style",
            ".post-nav", ".site-footer", ".site-header",
            ".ads", ".sidebar", ".toc", ".navigation"
        ]

        # HTML template
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

        # Spinner for progress indication
        self.spin_chars = "⠋⠙⠚⠞⠖⠦⠴⠲⠳⠓"

    def _create_backend(self) -> ScraperBackend:
        """Create the appropriate backend based on configuration"""
        retry_config = self.config.get('retry', {})

        if self.backend_name == 'aiohttp':
            return AioHttpBackend(self.user_agents, retry_config)
        elif self.backend_name == 'requests-html':
            return RequestsHtmlBackend(self.user_agents, retry_config)
        elif self.backend_name == 'playwright':
            return PlaywrightBackend(self.user_agents, retry_config)
        else:
            raise ValueError(f"Unsupported backend: {self.backend_name}")

    def _extract_website_name(self, url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc
        domain = re.sub(r'^www\.', '', domain)
        return re.sub(r'[^\w\-]', '_', domain)

    def _load_config(self, config_file: Optional[str] = None) -> Dict[str, Any]:
        default_config = {
            'rate_limiting': {'delay': 0.1, 'enabled': True},
            'retry': {'max_attempts': 3, 'backoff_factor': 0.5},
            'user_agent_rotation': {'enabled': True},
            'concurrency': {'max_concurrent': 10}
        }

        if config_file and os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    import yaml
                    file_config = yaml.safe_load(f)
                else:
                    file_config = json.load(f)

            def merge_dicts(default: Dict, override: Dict) -> Dict:
                result = default.copy()
                for key, value in override.items():
                    if isinstance(value, dict) and key in result:
                        result[key] = merge_dicts(result[key], value)
                    else:
                        result[key] = value
                return result

            return merge_dicts(default_config, file_config)
        return default_config

    def _parse_html_with_fallback(self, content: str) -> 'BeautifulSoup':
        """Parse HTML with fallback parsers (learned from simple scraper)"""
        from bs4 import BeautifulSoup
        parsers = ["lxml", "html.parser", "html5lib"]

        for parser in parsers:
            try:
                return BeautifulSoup(content, parser)
            except Exception:
                continue

        return BeautifulSoup(content, "html.parser")

    def _clean_html_content(self, soup: 'BeautifulSoup') -> 'BeautifulSoup':
        """Clean HTML content by removing unwanted elements (learned from simple scraper)"""
        # Remove unwanted tags
        for selector in self.unwanted_selectors:
            for element in soup.select(selector):
                element.decompose()

        return soup

    def _generate_smart_filename(self, index: int, url: str, title: str) -> str:
        """Generate smart filename from URL and title (learned from simple scraper)"""
        tail = url.rstrip("/").split("/")[-1].replace(".html", "")
        if not tail:
            tail = re.sub(r"[^\w\-]+", "-", title.strip().lower()) or "page"
        tail = re.sub(r"-{2,}", "-", tail).strip("-")
        return f"{index:02d}_{tail}.html"

    def _format_html_content(self, title: str, original_html: str) -> str:
        try:
            # Use parser fallback system
            soup = self._parse_html_with_fallback(original_html)

            # Extract title
            if not title or title == 'Home':
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()
                else:
                    title = "Scraped Page"

            # Clean unwanted elements
            soup = self._clean_html_content(soup)

            # Try enhanced content selectors (learned from simple scraper)
            inner_html = ""
            for selector in self.content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    inner_html = str(content_elem)
                    break

            # Fallback to body
            if not inner_html:
                body = soup.find('body')
                if body:
                    inner_html = str(body)
                else:
                    inner_html = str(soup)

            return self.html_template.format(title=title, inner_html=inner_html)

        except Exception as e:
            print(f"Error formatting HTML: {e}")
            return original_html

    async def __aenter__(self):
        await self.backend.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.backend.__aexit__(exc_type, exc_val, exc_tb)

    async def scrape_single_page(self, url: str) -> Optional[str]:
        """Scrape a single page with rate limiting"""
        if self.config.get('rate_limiting', {}).get('enabled', True):
            await asyncio.sleep(self.request_delay)

        return await self.backend.scrape_page(url)

    async def scrape_multiple_pages(self, pages: List[Tuple[str, str]]) -> None:
        """Scrape multiple pages with progress bar"""
        os.makedirs(self.output_dir, exist_ok=True)

        self.metrics.total_pages = len(pages)
        semaphore = asyncio.Semaphore(self.max_concurrent)

        print(f"\n🚀 Starting scrape with {self.backend_name} backend...")
        print(f"📊 Processing {len(pages)} pages with {self.max_concurrent} concurrent requests")

        async def progress_wrapper(title: str, url: str, pbar: tqdm) -> bool:
            async with semaphore:
                start_time = time.time()
                content = await self.scrape_single_page(url)

                if content:
                    formatted_content = self._format_html_content(title, content)
                    # Use smart filename generation (learned from simple scraper)
                    filename = self._generate_smart_filename(
                        pages.index((title, url)) + 1, url, title
                    )
                    filepath = os.path.join(self.output_dir, filename)

                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(formatted_content)

                    self.metrics.successful_pages += 1
                    self.metrics.total_size_mb += len(formatted_content) / (1024 * 1024)
                    page_time = time.time() - start_time
                    self.metrics.total_time += page_time
                else:
                    self.metrics.failed_pages += 1

                pbar.update(1)
                return content is not None

        with tqdm(total=len(pages), desc=f"Scraping ({self.backend_name})", unit="page") as pbar:
            tasks = [progress_wrapper(title, url, pbar) for title, url in pages]
            await asyncio.gather(*tasks)

        if self.metrics.successful_pages > 0:
            self.metrics.avg_time_per_page = self.metrics.total_time / self.metrics.successful_pages

    def print_metrics(self):
        print(f"\n{'='*60}")
        print(f"SCRAPING METRICS ({self.backend_name.upper()} BACKEND)")
        print(f"{'='*60}")
        print(f"Total pages processed: {self.metrics.total_pages}")
        print(f"Successful pages: {self.metrics.successful_pages}")
        print(f"Failed pages: {self.metrics.failed_pages}")
        print(f"Total time: {self.metrics.total_time:.2f}s")
        print(f"Average time per page: {self.metrics.avg_time_per_page:.2f}s")
        print(f"Total size: {self.metrics.total_size_mb:.2f} MB")
        print(f"{'='*60}")

# Backend availability checker
def check_backend_availability():
    """Check which backends are available"""
    backends = {
        'aiohttp': AIOHTTP_AVAILABLE,
        'requests-html': REQUESTS_HTML_AVAILABLE,
        'playwright': PLAYWRIGHT_AVAILABLE
    }

    print("🔍 Backend Availability:")
    for backend, available in backends.items():
        status = "✅ Available" if available else "❌ Not installed"
        print(f"  {backend}: {status}")

    return backends

if __name__ == "__main__":
    check_backend_availability()
