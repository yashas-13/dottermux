#!/usr/bin/env python3
"""
collect_secondary_sources.py — Collect Dubai real estate data from public secondary sources.
Sources: GitHub raw datasets, public Kaggle exports, known open-data URLs.
"""
import requests, csv, json, time
from pathlib import Path

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36",
    "Accept": "text/csv,application/json,*/*;q=0.8",
}

def download_file(url, out_path, expected_type=None):
    """Download a file with basic validation."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        if r.status_code == 200:
            content = r.content
            # Basic validation
            if expected_type == "csv" and not content.startswith(b"") and b"," not in content[:1000]:
                print(f"  [WARN] {url} - may not be CSV (no comma in first 1KB)")
            with open(out_path, "wb") as f:
                f.write(content)
            print(f"  [OK] {len(content):,} bytes -> {out_path}")
            return True
        else:
            print(f"  [ERR] {url} -> HTTP {r.status_code}")
            return False
    except Exception as e:
        print(f"  [ERR] {url} -> {e}")
        return False

def try_kaggle_bayut():
    """Download Bayut properties from known GitHub mirror."""
    url = "https://raw.githubusercontent.com/CS-JAM/466DataSet/main/bayut_selling_properties.csv"
    out = Path("dubai_bayut_properties.csv")
    if out.exists():
        print(f"  [SKIP] {out} already exists")
        return True
    return download_file(url, out, expected_type="csv")

def try_github_raw(repo, path, out_name):
    """Try to download from GitHub raw URL."""
    url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
    out = Path(out_name)
    return download_file(url, out, expected_type="csv")

def scan_github_repos():
    """Scan known Dubai real estate repos for raw data files."""
    repos = [
        ("logiover/propertyfinder-scraper", "data/"),
        ("CS-JAM/466DataSet", ""),
        ("HamzaShuja/Dubai-Land-Department-Analytics", "data/"),
        ("Arkaantos/Dubai_Land_Department_Transactions_Data_Analysis", "data/"),
        ("kdj06/Dubai-Land-Department", "data/"),
        ("level09/dld-mcp", ""),
    ]
    found = []
    for repo, subpath in repos:
        # Try to list files via GitHub API (no auth, rate limited)
        try:
            api_url = f"https://api.github.com/repos/{repo}/contents/{subpath}"
            r = requests.get(api_url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                items = r.json()
                for item in items:
                    if item["name"].endswith((".csv", ".json", ".xlsx", ".xls")):
                        download_url = item.get("download_url")
                        if download_url:
                            local_name = f"{repo.replace('/', '_')}_{item['name']}"
                            if download_file(download_url, local_name):
                                found.append((local_name, download_url))
        except Exception as e:
            print(f"  [GitHub] {repo}: {e}")
        time.sleep(1)  # Rate limit
    return found

def try_direct_sources():
    """Try known direct data URLs."""
    sources = [
        ("https://data.gov.ae/api/3/action/package_search?q=dubai+real+estate&rows=10", "dubai_data_gov_ae.json"),
        # Add any other known public endpoints
    ]
    for url, out_name in sources:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                with open(out_name, "w") as f:
                    json.dump(r.json(), f, indent=2)
                print(f"  [OK] JSON saved -> {out_name}")
        except Exception as e:
            print(f"  [ERR] {url}: {e}")

def main():
    print("=" * 60)
    print("SECONDARY SOURCE COLLECTION - Dubai Real Estate")
    print("=" * 60)
    
    results = {"downloaded": [], "skipped": [], "failed": []}
    
    # 1. Bayut properties (Kaggle via GitHub mirror)
    print("\n[1] Bayut properties (Kaggle via CS-JAM/466DataSet)")
    if try_kaggle_bayut():
        results["downloaded"].append("dubai_bayut_properties.csv")
    else:
        results["failed"].append("dubai_bayut_properties.csv")
    
    # 2. Scan GitHub repos for data files
    print("\n[2] Scanning GitHub repos for raw data files...")
    found = scan_github_repos()
    for name, url in found:
        results["downloaded"].append(f"{name} (from {url})")
    
    # 3. Try direct data.gov.ae
    print("\n[3] Trying data.gov.ae...")
    try_direct_sources()
    
    # 4. PropertyFinder scraper (if it has sample data)
    print("\n[4] Checking PropertyFinder scraper repo...")
    try_github_raw("logiover/propertyfinder-scraper", "sample_data.csv", "propertyfinder_sample.csv")
    try_github_raw("logiover/propertyfinder-scraper", "data.csv", "propertyfinder_data.csv")
    try_github_raw("logiover/propertyfinder-scraper", "dubai_properties.csv", "propertyfinder_dubai.csv")
    
    # 5. Check for any existing CSV files with Dubai data
    print("\n[5] Checking existing CSV files...")
    import glob
    for csv_file in glob.glob("*.csv"):
        try:
            import pandas as pd
            df = pd.read_csv(csv_file, nrows=1)
            cols = list(df.columns)
            # Check if it might contain Dubai data
            sample = pd.read_csv(csv_file, nrows=5)
            text = sample.to_string().lower()
            if "dubai" in text or "jvc" in text or "marina" in text or "downtown" in text:
                print(f"  [Dubai data?] {csv_file} - cols: {cols[:10]}")
                results["downloaded"].append(f"{csv_file} (existing, contains Dubai terms)")
        except Exception:
            pass
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for item in results["downloaded"]:
        print(f"  ✓ {item}")
    for item in results["failed"]:
        print(f"  ✗ {item}")
    for item in results["skipped"]:
        print(f"  - {item}")
    
    # Save results
    with open("secondary_collection_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Results saved to secondary_collection_results.json")

if __name__ == "__main__":
    main()