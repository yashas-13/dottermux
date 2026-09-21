#!/usr/bin/env python3
"""
dubai_re_scraper.py — Dubai Real Estate Buyers & Transactions Scraper
Sources: DLD public data, RERA project registry, open data portals
Outputs: dubai_buyers.csv, dubai_transactions.csv
"""
import csv, json, re, time, sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ============================================================
# SOURCE 1: DLD Open Data / Dubai Government datasets
# ============================================================
def fetch_dld_open_data():
    """Try Dubai Government open data portals for transaction data."""
    urls = [
        "https://data.gov.ae/api/3/action/package_search?q=dubai+real+estate+transaction&rows=20",
        "https://data.gov.ae/api/3/action/package_search?q=dubai+property+buyer&rows=20",
        "https://www.dubai.opendata.arcgis.com/datasets?f=json",
    ]
    results = []
    for url in urls:
        try:
            print(f"  [DLD] {url[:80]}")
            r = requests.get(url, headers=H, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if "result" in data and "results" in data["result"]:
                    for pkg in data["result"]["results"][:10]:
                        results.append({
                            "source": "data.gov.ae",
                            "title": pkg.get("title", ""),
                            "url": pkg.get("url", ""),
                            "resource_url": pkg.get("resources", [{}])[0].get("url", "") if pkg.get("resources") else "",
                            "format": pkg.get("resources", [{}])[0].get("format", "") if pkg.get("resources") else "",
                        })
                    print(f"    -> {len(results)} datasets found")
        except Exception as e:
            print(f"    -> ERR: {e}")
    return results

# ============================================================
# SOURCE 2: RERA Project Registry (public)
# ============================================================
def fetch_rera_projects():
    """Fetch RERA registered project data."""
    # RERA publishes project registry - try known endpoints
    urls = [
        "https://www.rera.ae/api/v1/projects?pageSize=20",
        "https://www.rera.ae/api/projects?pageSize=20",
    ]
    results = []
    for url in urls:
        try:
            print(f"  [RERA] {url[:80]}")
            r = requests.get(url, headers=H, timeout=15)
            if r.status_code == 200:
                data = r.json() if "json" in r.headers.get("content-type","") else {}
                if isinstance(data, list):
                    for p in data[:20]:
                        results.append({
                            "source": "rera",
                            "project_name": p.get("name", p.get("projectName", "")),
                            "developer": p.get("developer", ""),
                            "location": p.get("location", p.get("area", "")),
                            "units": p.get("units", p.get("totalUnits", "")),
                            "status": p.get("status", ""),
                            "url": p.get("url", ""),
                        })
                    print(f"    -> {len(results)} projects")
                else:
                    print(f"    -> response type: {type(data)}")
        except Exception as e:
            print(f"    -> ERR: {e}")
    return results

# ============================================================
# SOURCE 3: Scrape public Dubai property listing pages
# ============================================================
def scrape_property_pages():
    """Scrape public Dubai real estate listing/buyer pages."""
    search_urls = [
        "https://www.bayut.com/dubai/property-for-sale/",
        "https://www.propertyfinder.ae/en/dubai/property-for-sale",
        "https://www.dubai-land.gov.ae/en/dubai-real-estate-transaction-services",
    ]
    results = []
    for url in search_urls:
        try:
            print(f"  [Scrape] {url[:80]}")
            r = requests.get(url, headers=H, timeout=20)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                # Extract contact info, emails, phone numbers
                emails = set(re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-z]{2,}", r.text))
                phones = set(re.findall(r"(?:\+971|00971)?[\s\-]?[5][0-9]{8}", r.text))
                links = [a.get("href","") for a in soup.find_all("a", href=True) if "dubai" in (a.get("href","")).lower()][:20]
                
                results.append({
                    "source": "scrape",
                    "url": url,
                    "emails": list(emails)[:10],
                    "phones": list(phones)[:10],
                    "links": links,
                    "title": soup.title.string.strip() if soup.title and soup.title.string else "",
                })
                print(f"    -> emails:{len(emails)} phones:{len(phones)} links:{len(links)}")
        except Exception as e:
            print(f"    -> ERR: {e}")
    return results

# ============================================================
# SOURCE 4: Google dork-driven search via Brave Search API (free)
# ============================================================
def brave_search_dorks():
    """Use Brave Search API to find Dubai real estate data files."""
    dorks = [
        'filetype:csv "dubai" "buyer" OR "investor" OR "transaction"',
        'filetype:xlsx "dubai real estate" property data',
        'filetype:json "dubai" "property" "buyer"',
        'filetype:csv "dubai land department" transaction',
        'filetype:pdf "dubai" "property investor" "contact"',
        'site:dld.gov.ae filetype:pdf transaction OR registration',
        'site:data.gov.ae filetype:csv real estate',
        'filetype:csv "dubai" "sales" "transactions" "2024" OR "2025"',
        'filetype:xlsx "dubai" "unit" "price" "area" "bedrooms"',
        'site:bayut.com OR site:propertyfinder.ae filetype:pdf "market report"',
    ]
    results = []
    try:
        # Try free Brave Search API endpoint
        for dork in dorks:
            url = f"https://search.brave.com/search?q={requests.utils.quote(dork)}&source=web"
            print(f"  [Brave] {dork[:80]}")
            r = requests.get(url, headers=H, timeout=15)
            if r.status_code == 200 and len(r.text) > 500:
                soup = BeautifulSoup(r.text, "html.parser")
                links = []
                for a in soup.select("a[href]"):
                    href = a.get("href","")
                    if href.startswith("http") and "search.brave.com" not in href:
                        links.append({"url": href, "title": a.get_text(strip=True)[:200]})
                results.append({"dork": dork, "results": links[:10]})
                print(f"    -> {len(links)} results")
            time.sleep(3)
    except Exception as e:
        print(f"  [Brave] ERR: {e}")
    return results

# ============================================================
# SOURCE 5: GitHub — search for Dubai real estate datasets
# ============================================================
def github_dubai_data():
    """Search GitHub for Dubai real estate open data."""
    queries = [
        "dubai real estate csv",
        "dubai property transactions json",
        "dubai land department data",
        "dubai buyers investors data",
    ]
    results = []
    try:
        for q in queries:
            url = f"https://api.github.com/search/repositories?q={requests.utils.quote(q)}&per_page=5"
            print(f"  [GitHub] {q[:60]}")
            r = requests.get(url, headers=H, timeout=15)
            if r.status_code == 200:
                data = r.json()
                for repo in data.get("items", [])[:5]:
                    results.append({
                        "repo": repo.get("full_name",""),
                        "url": repo.get("html_url",""),
                        "description": repo.get("description",""),
                        "stars": repo.get("stargazers_count",0),
                    })
                print(f"    -> {data.get('total_count',0)} repos")
            time.sleep(2)
    except Exception as e:
        print(f"  [GitHub] ERR: {e}")
    return results

# ============================================================
# Main — run all sources and save to CSV/JSON
# ============================================================
def main():
    print("=" * 60)
    print("DUBAI REAL ESTATE SCRAPER")
    print("Sources: DLD, RERA, Property Portals, Brave, GitHub")
    print("=" * 60)

    all_data = {
        "datasets": [],
        "projects": [],
        "contacts": [],
        "dork_results": [],
        "github_repos": [],
    }

    # 1. DLD / Open Data
    print("\n[1/5] Dubai Open Data Portals...")
    all_data["datasets"] = fetch_dld_open_data()

    # 2. RERA Projects
    print("\n[2/5] RERA Projects...")
    all_data["projects"] = fetch_rera_projects()

    # 3. Scrape property portals
    print("\n[3/5] Property Portal Scraping...")
    all_data["contacts"] = scrape_property_pages()

    # 4. Brave dork search
    print("\n[4/5] Brave Search Dorks...")
    all_data["dork_results"] = brave_search_dorks()

    # 5. GitHub search
    print("\n[5/5] GitHub Search...")
    all_data["github_repos"] = github_dubai_data()

    # Save JSON
    out_json = Path("dubai_re_raw.json")
    with open(out_json, "w") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"\n[*] JSON saved: {out_json}")

    # Save buyers CSV
    csv_path = Path("dubai_buyers.csv")
    fields = ["source","title","url","project_name","developer","location","units","status","emails","phones","dork","repo","stars"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        # Flatten dataset entries
        for d in all_data["datasets"]:
            w.writerow({
                "source": d.get("source",""),
                "title": d.get("title",""),
                "url": d.get("resource_url", d.get("url","")),
                "project_name": "", "developer": "", "location": "", "units": "", "status": "",
                "emails": "", "phones": "", "dork": "", "repo": "", "stars": "",
            })
        # Flatten project entries
        for p in all_data["projects"]:
            w.writerow({
                "source": p.get("source",""),
                "title": "", "url": "",
                "project_name": p.get("project_name",""),
                "developer": p.get("developer",""),
                "location": p.get("location",""),
                "units": p.get("units",""),
                "status": p.get("status",""),
                "emails": "", "phones": "", "dork": "", "repo": "", "stars": "",
            })
        # Flatten contact/scrape entries
        for c in all_data["contacts"]:
            for email in c.get("emails", []):
                w.writerow({
                    "source": "contact",
                    "title": c.get("title",""),
                    "url": c.get("url",""),
                    "project_name": "", "developer": "", "location": "", "units": "", "status": "",
                    "emails": email, "phones": "", "dork": "", "repo": "", "stars": "",
                })
            for phone in c.get("phones", []):
                w.writerow({
                    "source": "contact",
                    "title": c.get("title",""),
                    "url": c.get("url",""),
                    "project_name": "", "developer": "", "location": "", "units": "", "status": "",
                    "emails": "", "phones": phone, "dork": "", "repo": "", "stars": "",
                })
        # Dork results
        for d in all_data["dork_results"]:
            for r in d.get("results", []):
                w.writerow({
                    "source": "dork",
                    "title": r.get("title",""),
                    "url": r.get("url",""),
                    "project_name":"", "developer":"", "location":"", "units":"", "status":"",
                    "emails":"", "phones":"", "dork": d.get("dork",""), "repo":"", "stars":"",
                })
        # GitHub repos
        for g in all_data["github_repos"]:
            w.writerow({
                "source": "github",
                "title": g.get("description",""),
                "url": g.get("url",""),
                "project_name":"", "developer":"", "location":"", "units":"", "status":"",
                "emails":"", "phones":"", "dork":"", "repo":g.get("repo",""), "stars":g.get("stars",""),
            })

    print(f"[*] CSV saved: {csv_path}")
    
    # Summary
    total_rows = sum(len(d.get("results",[])) for d in all_data["dork_results"])
    total_emails = sum(len(c.get("emails",[])) for c in all_data["contacts"])
    total_phones = sum(len(c.get("phones",[])) for c in all_data["contacts"])
    print(f"\n[+] SUMMARY")
    print(f"    Datasets found: {len(all_data['datasets'])}")
    print(f"    Projects found: {len(all_data['projects'])}")
    print(f"    Emails found: {total_emails}")
    print(f"    Phones found: {total_phones}")
    print(f"    Dork result links: {total_rows}")
    print(f"    GitHub repos: {len(all_data['github_repos'])}")
    print(f"    JSON: {out_json}")
    print(f"    CSV: {csv_path}")

if __name__ == "__main__":
    main()
