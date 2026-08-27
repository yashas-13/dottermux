# NoBroker Bangalore Property Scraper

Multi-threaded web scraper for Nobroker.in Bangalore rental property listings. Extracts property details and saves them directly to CSV.

## Features
- **Multi-threaded Scraping**: Fast concurrent page fetching using Python's `ThreadPoolExecutor`.
- **Robust Parsers**: Resolves encoding mismatches (like garbled Indian Rupee symbols) and handles dynamic DOM selector patterns.
- **Pre-Authenticated Sessions**: Supports cookie injection (`nobroker_cookies.json`) to bypass anti-scraping checks via phone/OTP login.
- **Incremental Writing**: Flushes to CSV continuously to prevent data loss.
- **Resilient Retry Mechanism**: Configurable request retries with backoff factors to handle rate limits gracefully.

## Fields Scraped
- Title
- Address
- Rent (Rs)
- Deposit (Rs)
- Size (Acres/Sqft)
- Furnishing
- Property Age
- Available For
- Immediate Possession
- Phone Number (if available/authenticated)

## Getting Started

1. **Install Dependencies**:
   ```bash
   pip install beautifulsoup4 requests progressbar
   ```

2. **Run Scraper**:
   ```bash
   python3 scrape_bangalore.py
   ```

3. **Provide Cookies (Optional for Authenticated Scrapes)**:
   Generate the cookie template:
   ```bash
   python3 -c "from scrape_bangalore import generate_sample_cookies; generate_sample_cookies()"
   ```
   Modify `nobroker_cookies.json` with actual cookies from your browser session to fetch authenticated data.
