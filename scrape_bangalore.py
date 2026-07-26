#!/usr/bin/env python3
"""
Multi-threaded Nobroker Bangalore rental scraper with incremental CSV writing.
Supports pre-authenticated sessions (phone/OTP) via cookie injection.
"""

import csv
import json
import os
import random
import re
import threading
import time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================== CONFIG ==================
BASE_URL = "https://www.nobroker.in/property/rent/bangalore/Bangalore/"
SEARCH_PARAM = "W3sibGF0IjoxMi45NzE2LCJsb24iOjc3LjU5NDYsInNob3dNYXAiOmZhbHNlLCJwbGFjZUlkIjoiQ2hJSllVZzVUdU93VXFJN09nN1FJZz09IiwicGxhY2VOYW1lIjoiQmFuZ2Fsb3JlIiwiY2l0eSI6ImJhbmdhbG9yZSJ9XQ=="
MAX_PAGES = 1000
MAX_WORKERS = 4
BATCH_SIZE = 25
OUTPUT_FILE = "bangalore_rent_final.csv"
ERROR_FILE = "bangalore_rent_errors.jsonl"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
}

# ================== HELPERS ==================
def extract_number(text):
    """Extract numeric value from text, handling superscript characters and currency symbols."""
    if not text or text == '-':
        return '-'
    # Normalize superscript characters
    text = text.replace('¹', '1').replace('²', '2').replace('³', '3')
    # Extract digits
    digits = ''.join(filter(str.isdigit, text))
    return int(digits) if digits else '-'

def extract_details(article):
    """Extract Furnishing, Apartment Type, Preferred Tenants, Available From from article."""
    details = {}
    for div in article.find_all('div', class_='font-semibold'):
        value = div.text.strip()
        label_div = div.find_next_sibling()
        if label_div:
            label = label_div.text.strip()
            if 'Furnishing' in label or 'Furnished' in label:
                details['Furnishing'] = value
            elif 'Apartment Type' in label:
                details['Property Age'] = value
            elif 'Preferred Tenants' in label:
                details['Preferred Tenants'] = value
            elif 'Available From' in label:
                details['Available From'] = value
    return details

def extract_phone_number(article):
    """Extract phone number from article if available."""
    # Try to find phone number in various locations
    phone_patterns = [
        r'\+?\d{1,2}\s?\d{3,5}\s?\d{3,5}',
        r'\+?\d{10,15}',
        r'\d{5}\s\d{5}'
    ]
    
    # Look for phone-like texts in the article
    for element in article.find_all(string=True):
        text = element.strip()
        # Check if it looks like a phone number
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group()
                # Clean up formatting
                phone = re.sub(r'\s+', ' ', phone)
                phone = phone.replace('-', ' ')
                return phone
    
    # Also check common phone container classes
    phone_container = article.find('div', class_=lambda x: x and 'phone' in x.lower())
    if phone_container:
        return phone_container.text.strip()
    
    return '-'

def parse_article(art):
    """Parse single article element, return dict or None on failure."""
    try:
        # Title
        title_h2 = art.find('h2', class_=lambda x: x and 'heading-6' in x and 'font-semi-bold' in x)
        title = title_h2.text.strip() if title_h2 else '-'

        # Address
        addr_div = art.find('div', class_=lambda x: x and 'text-gray-light' in x)
        address = addr_div.text.strip() if addr_div else '-'

        # Rent
        rent_div = art.find('div', id='minimumRent')
        if rent_div:
            rent_text = rent_div.text.split('+')[0]
            rent = extract_number(rent_text)
        else:
            rent = '-'

        # Deposit
        deposit_div = art.find('div', id='roomType')
        deposit = extract_number(deposit_div.text) if deposit_div else '-'

        # Area (Size)
        area_div = art.find('div', id='unitCode')
        area = extract_number(area_div.text) if area_div else '-'

        # Property details (Furnishing, etc.)
        details = extract_details(art)
        
        # Extract phone number
        phone = extract_phone_number(art)

        # Build result
        result = {
            'title': title,
            'address': address,
            'rent': rent,
            'deposit': deposit,
            'size': area,
            'furnishing': details.get('Furnishing', '-'),
            'property_age': details.get('Property Age', '-'),
            'available_for': details.get('Preferred Tenants', '-'),
            'immediate_possession': details.get('Available From', '-'),
            'phone_number': phone
        }
        
        return result
    except Exception:
        return None

def create_session(cookies=None):
    """Create requests session with retry strategy and optional cookies."""
    s = Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.headers.update(HEADERS)
    if cookies:
        s.cookies.update(cookies)
    return s

def fetch_page(session, page_num):
    """Fetch a single page, return list of parsed listings."""
    url = f"{BASE_URL}?searchParam={SEARCH_PARAM}&sharedAccomodation=0&orderBy=nbRank,desc&radius=2&traffic=true&travelTime=30&propertyType=rent&pageNo={page_num}"
    try:
        resp = session.get(url, timeout=20)
        # Force encoding to utf-8 to prevent garbled rupee symbols / superscript mapping bugs
        resp.encoding = 'utf-8'
        if resp.status_code == 404:
            return None, "404"
        if len(resp.text) < 10000 or 'captcha' in resp.text.lower():
            return None, "blocked"
        resp.raise_for_status()
    except Exception as e:
        return None, str(e)

    soup = BeautifulSoup(resp.text, 'html.parser')
    articles = soup.find_all('article')
    if not articles:
        return None, "empty"

    results = []
    for art in articles:
        parsed = parse_article(art)
        if parsed:
            parsed['page'] = page_num
            results.append(parsed)
    return results, None

# ================== CSV WRITER THREAD ==================
class CSVWriter:
    def __init__(self, filename, fieldnames):
        self.filename = filename
        self.fieldnames = fieldnames
        self.queue = Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.thread.start()
        # Write header
        with open(self.filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(self.fieldnames)

    def write(self, row_dict):
        self.queue.put(row_dict)

    def _writer_loop(self):
        batch = []
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                item = self.queue.get(timeout=0.5)
                batch.append(item)
                if len(batch) >= BATCH_SIZE:
                    self._flush(batch)
                    batch = []
                self.queue.task_done()
            except:
                if batch:
                    self._flush(batch)
                    batch = []

    def _flush(self, batch):
        if not batch:
            return
        key_map = {
            'Title': 'title',
            'Address': 'address',
            'Rent(Rs)': 'rent',
            'Deposit(Rs)': 'deposit',
            'Size(Acres)': 'size',
            'Furnishing': 'furnishing',
            'Property age': 'property_age',
            'Available for': 'available_for',
            'Immediate possession': 'immediate_possession',
            'Phone Number': 'phone_number'
        }
        with open(self.filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for item in batch:
                writer.writerow([item.get(key_map[fn], '-') for fn in self.fieldnames])

    def shutdown(self):
        self.stop_event.set()
        self.thread.join(timeout=5)
        # Final flush
        batch = []
        while not self.queue.empty():
            batch.append(self.queue.get())
        self._flush(batch)

# ================== ERROR LOGGER ==================
def log_error(page, error, session_id):
    with open(ERROR_FILE, 'a') as f:
        f.write(json.dumps({'page': page, 'error': error, 'session': session_id, 'time': time.time()}) + '\n')

# ================== MAIN ==================
def worker(page_queue, writer, session_id, cookies=None):
    session = create_session(cookies)
    while True:
        try:
            page = page_queue.get_nowait()
        except:
            break

        # Random delay
        time.sleep(random.uniform(1.0, 3.0))

        results, error = fetch_page(session, page)
        if error:
            log_error(page, error, session_id)
            print(f"[Worker-{session_id}] Page {page}: {error}")
            page_queue.task_done()
            continue

        for listing in results:
            writer.write(listing)
        page_queue.task_done()

    print(f"[Worker-{session_id}] Completed")

def load_cookies(path='nobroker_cookies.json'):
    """Load cookies from JSON file if exists."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def generate_sample_cookies():
    """Generate a sample cookies JSON for phone/OTP authentication."""
    # Note: Actual phone/OTP authentication would require handling session cookies
    # This is just a template - users should replace with their actual cookies
    sample_cookies = {
        "sessionid": "sample_session_id",
        "csrftoken": "sample_csrf_token"
    }
    with open('nobroker_cookies.json', 'w') as f:
        json.dump(sample_cookies, f, indent=2)
    print("Generated nobroker_cookies.json template - replace with actual phone/OTP auth cookies")

def main():
    # Try to load existing cookies
    cookies = load_cookies()
    if not cookies:
        print("No auth cookies found. Running unauthenticated.")
        print("For phone/OTP authentication, generate a cookie template:")
        print("  python3 -c 'from scrape_bangalore_final import generate_sample_cookies; generate_sample_cookies()'")
        print("Replace the template with actual cookies from phone/OTP login.")
    else:
        print("Loaded authenticated cookies")

    # Queue pages
    page_queue = Queue()
    for p in range(1, MAX_PAGES + 1):
        page_queue.put(p)

    # CSV writer with phone number support
    fieldnames = ['Title', 'Address', 'Rent(Rs)', 'Deposit(Rs)', 'Size(Acres)',
                  'Furnishing', 'Property age', 'Available for', 'Immediate possession',
                  'Phone Number']
    writer = CSVWriter(OUTPUT_FILE, fieldnames)

    # Start workers
    print(f"Starting {MAX_WORKERS} workers for {MAX_PAGES} pages...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for i in range(MAX_WORKERS):
            futures.append(executor.submit(worker, page_queue, writer, i, cookies))
        # Wait for completion
        for f in as_completed(futures):
            f.result()

    writer.shutdown()
    print(f"\nDone! Data saved to {OUTPUT_FILE}")
    print("Total listings collected including phone numbers")

if __name__ == '__main__':
    main()