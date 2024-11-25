# Atlys Web Scraper

A flexible and efficient web scraper built with Python. It fetches product data from e-commerce websites, stores it using a pluggable storage strategy, and supports caching with Redis.

## Features
- **Authentication**: Supports `Bearer` token for authenticated requests.
- **Crawl Delays**: Respects delays between requests for ethical scraping.
- **Error Handling**: Retries on request failures with configurable retry logic.
- **Caching**: Caches product data in Redis with a 24-hour expiration.
- **Pluggable Storage**: Save data in JSON files or databases (default SQLite).
- **Product Parsing**: Extracts product details such as name, price, and image.

## Requirements
- Python 3.7+
- Redis server (optional for caching)

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/web-scraper.git
   cd web-scraper
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up Redis (if needed):
   ```bash
   redis-server
   ```
4. Start proxy server (if using):
   ```bash
   proxy --hostname 0.0.0.0 --port 9000
   ```
## Usage
1. Update the `BASE_URL`, `MAX_PAGE`, and other configurations in the `__main__` section of `scraper.py`.
2. Run the scraper:
   ```bash
   python scraper.py
   ```

## Configuration
- **Base URL**: The e-commerce site URL to scrape.
- **Auth Token**: Add an authentication token if required.
- **Storage**: Choose between `JsonFileStorage` or `DatabaseStorage`.
- **Redis Cache**: Enable for faster repeated scrapes.

## Logging
Logs are written to `scraper.log` and displayed in the console.

## Example
Scraping products from a e-commerce site:
```python
scraper = WebScraper(
    base_url="https://example.com/shop/",
    auth_token="your-auth-token",
    redis_url="redis://localhost:6379/0"
)
scraper.scrape(max_page=5)