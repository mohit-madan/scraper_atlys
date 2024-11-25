import requests
from bs4 import BeautifulSoup, Tag
import logging
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import random
from typing import Optional, List, Dict, Any
import redis
from datetime import timedelta
from storage import StorageStrategy, JsonFileStorage,DatabaseStorage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler()
    ]
)

class WebScraper:
    def __init__(
        self, 
        base_url: str, 
        storage_strategy: Optional[StorageStrategy] = None,
        db_url: str = 'sqlite:///scraper.db',
        user_agent: str = 'MyScraperBot/1.0',
        auth_token: Optional[str] = None,
        redis_url: str = 'redis://localhost:6379/0',
        proxy: Optional[Dict[str, str]] = None
    ):
        self.base_url = base_url.rstrip('/')  # Ensure no trailing slash
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Authorization': f'Bearer {auth_token}' if auth_token else ''
        })
        
        # Add proxy configuration if provided
        if proxy:
            self.session.proxies.update(proxy)
            logging.info(f"Using proxy: {proxy}")
        
        self.delay = 1  # Default delay
        logging.info(f"Using default delay of {self.delay} seconds")
    
        # Initialize the database with better error handling
        try:
            self.engine = create_engine(db_url)
            self.Session = sessionmaker(bind=self.engine)
            self.db_session = self.Session()
            logging.info(f"Database initialized at {db_url}")
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            raise
        
        # Initialize storage strategy
        self.storage_strategy = storage_strategy or JsonFileStorage()
        self.products: List[Dict[str, Any]] = []
        
        # Initialize Redis with better error handling
        try:
            self.redis_client = redis.from_url(redis_url)
            self.redis_client.ping()  # Test connection
            logging.info(f"Redis cache initialized at {redis_url}")
        except redis.ConnectionError as e:
            logging.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def clean_price(self, price_str: Optional[str]) -> Optional[str]:
        """Clean price strings by removing currency symbols and whitespace."""
        if not price_str:
            return None
        return price_str.strip().replace('₹', '').replace('\u20b9', '').strip()

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, max_retries: int = 3, retry_delay: int = 5) -> Optional[str]:
        for attempt in range(max_retries):
            try:
                # Check if Authorization header is present
                if not self.session.headers.get('Authorization'):
                    logging.warning("No authentication token provided")
                
                # Try with SSL verification first
                try:
                    response = self.session.get(url, params=params, timeout=10)
                except requests.exceptions.SSLError:
                    logging.warning("SSL verification failed, retrying without verification")
                    response = self.session.get(url, params=params, timeout=10, verify=False)
                
                # Handle authentication errors
                if response.status_code == 401:
                    logging.error("Authentication failed: Invalid or missing token")
                    return None
                
                response.raise_for_status()
                logging.info(f"Successfully fetched: {url}")
                time.sleep(self.delay + random.uniform(0, 1))
                return response.text
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"All {max_retries} attempts failed for {url}: {e}")
        return None
    
    def parse(self, html_content: str) -> BeautifulSoup:
        soup = BeautifulSoup(html_content, 'html.parser')
        products: List[Tag] = soup.find_all('li', class_='type-product')
        if not products:
            products = soup.find_all('li', class_='product')
        if not products:
            products = soup.find_all('li')
        
        self.products_found_in_page = len(products)
        logging.info(f"Found {self.products_found_in_page} products")
        
        for product in products:
            try:
                # Extract title and URL with better error handling
                title_element = product.find('h2', class_='woo-loop-product__title')
                name = None
                product_url = None
                
                if title_element and title_element.a:
                    name = title_element.a.get_text(strip=True)
                    product_url = title_element.a.get('href', '').strip()
                    if product_url:
                        url_name = product_url.split('product/')[-1].rstrip('/')
                        url_name = url_name.split('/')[-1]
                        name = ' '.join(url_name.split('-')).title()
                
                if not name or not product_url:
                    logging.warning("Skipping product with missing name or URL")
                    continue
                
                # Extract price with better error handling
                price = None
                regular = None
                sale_price = False
                
                price_element = product.find('span', class_='price')
                if price_element:
                    sale_elem = price_element.find('ins')
                    regular_elem = price_element.find('del')
                    
                    if sale_elem and sale_elem.find('bdi'):
                        price = self.clean_price(sale_elem.find('bdi').get_text())
                        regular = self.clean_price(regular_elem.find('bdi').get_text()) if regular_elem else None
                        sale_price = True
                    elif price_element.find('bdi'):
                        price = self.clean_price(price_element.find('bdi').get_text())
                        regular = price
                
                if not price:
                    logging.warning(f"No price found for product: {name}")
                    continue
                
                # Extract image with better error handling
                image_url = None
                image = product.find('img')
                if image:
                    # Try multiple image sources
                    image_url = (
                        image.get('data-src') or 
                        image.get('data-lazy-src') or 
                        image.get('src')
                    )
                    
                    if image_url and image_url.startswith('data:image/svg'):
                        srcset = image.get('srcset', '').strip()
                        if srcset:
                            image_url = srcset.split(',')[0].split(' ')[0]
                
                # Create product dictionary
                product_data = {
                    "product_title": name,
                    "product_url": product_url,
                    "product_price": price,
                    "regular_price": regular or price,
                    "path_to_image": image_url,
                    "on_sale": sale_price
                }
                
                # Check cache if Redis is available
                if self.redis_client and product_url:
                    try:
                        cached_price = self.redis_client.get(product_url)
                        if cached_price:
                            cached_price = cached_price.decode('utf-8')
                            if cached_price == price:
                                logging.info(f"Product price unchanged, skipping update: {name}")
                                continue
                        
                        # Store new price in cache
                        self.redis_client.setex(
                            product_url,
                            timedelta(hours=24),
                            price
                        )
                    except redis.RedisError as e:
                        logging.error(f"Redis error for product {name}: {e}")
                
                self.products.append(product_data)
                
            except Exception as e:
                logging.error(f"Error parsing product: {e}")
                continue
        
        return soup
    
    def scrape(self, max_page: int = 1) -> None:
        self.products = []  # Reset products list
        total_products_found = 0
        total_products_cached = 0
        saved_products = 0
        
        for page_num in range(1, max_page + 1):
            # Construct page URL
            page_url = f"{self.base_url}/page/{page_num}/" if page_num > 1 else f"{self.base_url}/"
            logging.info(f"Scraping page {page_num}: {page_url}")
            
            page_content = self.get(page_url)
            if page_content:
                products_before = len(self.products)
                self.parse(page_content)
                products_found_this_page = len(self.products) - products_before
                total_products_found += self.products_found_in_page
                total_products_cached += (self.products_found_in_page - products_found_this_page)
            else:
                logging.error(f"Failed to retrieve page {page_num}.")
                break
        
        # Save products with better error handling
        if not self.products:
            logging.warning("No products to save")
            saved_products = 0
        else:
            try:
                result = self.storage_strategy.save_products(self.products)
                if isinstance(result, bool):
                    saved_products = len(self.products) if result else 0
                elif isinstance(result, int):
                    saved_products = result
                else:
                    saved_products = 0
                    logging.warning("Unexpected return type from storage strategy")
            except Exception as e:
                logging.error(f"Error saving products: {e}")
                if isinstance(self.storage_strategy, DatabaseStorage):
                    logging.info("Attempting to update existing products...")
                    try:
                        result = self.storage_strategy.update_existing_products(self.products)
                        saved_products = result if isinstance(result, int) else 0
                    except Exception as update_error:
                        logging.error(f"Error updating products: {update_error}")
                        saved_products = 0
        
        # Print summary
        print("\n=== Scraping Session Summary ===")
        print(f"Total products found: {total_products_found}")
        print(f"Products skipped (cached): {total_products_cached}")
        print(f"Products successfully saved: {saved_products}")
        print("===============================\n")

    def __del__(self):
        """Cleanup method to close database session."""
        try:
            if hasattr(self, 'db_session'):
                self.db_session.close()
        except Exception as e:
            logging.error(f"Error closing database session: {e}")

if __name__ == "__main__":
    BASE_URL = "https://dentalstall.com/shop"
    MAX_PAGE = 2
    AUTH_TOKEN = "secret-token"
    REDIS_URL = "redis://localhost:6379/0"
    PROXY = {
        'http': 'http://localhost:9000',
        'no_proxy': 'localhost,127.0.0.1:9000'
    }
    
    try:
        scraper = WebScraper(
            BASE_URL, 
            storage_strategy=None,
            auth_token=AUTH_TOKEN, 
            redis_url=REDIS_URL,
            proxy=PROXY
        )
        
        scraper.storage_strategy = DatabaseStorage(scraper.db_session)    
        scraper.scrape(MAX_PAGE)
    except requests.exceptions.ProxyError as e:
        logging.error(f"Proxy connection failed: {e}. Falling back to direct connection.")
        scraper.session.proxies.clear()
        scraper.scrape(MAX_PAGE)
    except Exception as e:
        logging.error(f"Scraping failed: {e}")
    finally:
        if 'scraper' in locals():
            del scraper  # Ensure cleanup