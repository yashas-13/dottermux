#!/usr/bin/env python3
"""
dubai_dld_fetch.py — Fetch Dubai Land Department open data with retry/rate-limit handling.
API: https://gateway.dubailand.gov.ae/open-data (keyless, may require specific headers)
"""
import requests, json, csv, time, sys
from datetime import datetime, timedelta

BASE = "https://gateway.dubailand.gov.ae/open-data"
UA = "pipeworx-mcp-dubai-land/1.0 (+https://pipeworx.io)"
MAX_LIMIT = 200
DEFAULT_LIMIT = 50

# ── Helpers ──────────────────────────────────────────────────────────────

def to_dld_date(value):
    """Convert ISO date 'YYYY-MM-DD' to DLD format MM/DD/YYYY."""
    if value is None or value == "":
        return ""
    s = str(value).strip()
    m = __import__("re").match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return f"{m[2]}/{m[3]}/{m[1]}"
    # Already in MM/DD/YYYY
    if __import__("re").match(r"^\d{2}/\d{2}/\d{4}$", s):
        return s
    return s

def clamp_limit(n):
    n = int(n)
    if n < 1:
        return str(DEFAULT_LIMIT)
    if n > MAX_LIMIT:
        n = MAX_LIMIT
    return str(n)

def clamp_offset(n):
    n = int(n)
    if n < 0:
        return "0"
    return str(n)

def parse_body(raw_text):
    """Extract JSON from HTML error responses — looks for embedded <script> or data-blocks."""
    import re
    # Try to find JSON object in the body
    m = re.search(r"(\{.*\})", raw_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None

def safe_post(command, body, retries=3, backoff=3):
    """POST to DLD API with exponential backoff on 5xx."""
    headers = {"User-Agent": UA, "Content-Type": "application/json"}
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(f"{BASE}/{command}", headers=headers, json=body, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if data.get("responseCode") == 200:
                    return data, 0  # success
                # Application-level error
                return data, r.status_code
            if r.status_code >= 500:
                # Server error — exponential backoff
                wait = backoff * (2 ** (attempt - 1))
                print(f"    [{command}] 500 on attempt {attempt}/{retries}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            # 4xx or other — stop retrying
            print(f"    [{command}] HTTP {r.status_code}: {r.text[:200]}")
            return {"responseCode": r.status_code, "error": r.text[:200]}, r.status_code
        except Exception as e:
            wait = backoff * (2 ** (attempt - 1))
            print(f"    [{command}] Exception on attempt {attempt}/{retries}: {e}, retrying in {wait}s...")
            time.sleep(wait)
    # Exhausted retries
    print(f"    [{command}] Failed after {retries} attempts — likely service issue.")
    return {"responseCode": -1, "error": "max retries exhausted"}, -1

# ── DLD API commands ────────────────────────────────────────────────────

def fetch_dld(command, params, limit=DEFAULT_LIMIT, offset=0, sort="", retries=3):
    """Generic DLD fetch with retry logic."""
    body = {
        **params,
        "P_TAKE": str(limit),
        "P_SKIP": str(offset),
        "P_SORT": sort,
    }
    # Ensure required fields with defaults (based on upstream schema)
    for k in ["P_FROM_DATE", "P_TO_DATE", "P_GROUP_ID", "P_IS_OFFPLAN",
              "P_IS_FREE_HOLD", "P_AREA_ID", "P_USAGE_ID", "P_PROP_TYPE_ID",
              "P_DATE_TYPE", "P_PRJ_TYPE_ID", "P_PRJ_STATUS", "P_ZONE_ID",
              "P_NAME", "P_LAND_TYPE_ID", "P_IS_LEASE_HOLD", "P_GENDER",
              "P_VERSION"]:
        if k not in body:
            body[k] = ""
    
    result, status = safe_post(command, body, retries=retries)
    if status == -1:
        return [], 0
    
    if result.get("responseCode") != 200:
        # Small attempt: maybe body missing some keys; try with just command-specific fields
        print(f"    [{command}] responseCode={result.get('responseCode')}")
        return [], 0
    
    data = result.get("response", {})
    rows = data.get("result", []) or []
    # Strip noise columns
    NOISE = {"RN", "TOTAL", "DEFAULT_SORT"}
    clean = []
    for r in rows:
        r = {k: v for k, v in r.items() if k not in NOISE}
        clean.append(r)
    total = int(rows[0].get("TOTAL", len(rows))) if rows else 0
    return clean, total

# ── Convenience wrappers ────────────────────────────────────────────────

def fetch_transactions(params, limit=200, retries=3):
    return fetch_dld("transactions", params, limit=limit, retries=retries)

def fetch_areas(retries=3):
    return fetch_dld("carea-lookup", {}, limit=200, retries=retries)

# ── CSV output ──────────────────────────────────────────────────────────

def save_csv(rows, path, fields=None):
    if not rows:
        print(f"  [CSV] No rows to save to {path}")
        return
    if fields is None:
        fields = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  [CSV] Saved {len(rows)} rows to {path}")

# ── Main ────────────────────────────────────────────────────────────────

def main():
    today = datetime.now()
    from_date = datetime(today.year, 1, 1)
    to_date = today

    print("=" * 60)
    print(f"DLD DATA FETCH: {from_date.date()} to {to_date.date()}")
    print("=" * 60)

    all_sales = []
    for i in range(0, 1000, 200):
        rows, total = fetch_transactions({
            "P_FROM_DATE": "01/01/2024",
            "P_TO_DATE": "12/31/2024",
            "P_GROUP_ID": "1",
            "P_TAKE": "200",
            "P_SKIP": str(i),
            "P_SORT": "TRANS_VALUE_DESC",
        }, limit=200, retries=3)
        if rows:
            all_sales.extend(rows)
            print(f"  Fetched {len(rows)} (running total={len(all_sales)})")
        else:
            print(f"  No rows — likely API issue, stopping fetch.")
            break
        time.sleep(2)  # Respectful pause

    if all_sales:
        # Keep only useful columns
        useful = ["TRANSACTION_NUMBER", "INSTANCE_DATE", "AREA_EN",
                  "TRANS_VALUE", "PROPERTY_TYPE_ID", "PROJECT_EN", "P_IS_OFFPLAN"]
        out = []
        for r in all_sales:
            o = {k: r.get(k, "") for k in useful}
            out.append(o)
        save_csv(out, "dubai_dld_transactions.csv", fields=useful)
        print(f"  → Saved {len(out)} transaction records")
    else:
        print("  ⚠ No transaction data collected — DLD API may be temporarily unavailable.")
        print("  → Available fallback: dubai_bayut_properties.csv (41,381 rows from Kaggle)")

    # Areas
    print("\n[6] DLD Areas (Reference)")
    rows, total = fetch_areas(retries=3)
    if rows:
        save_csv(rows, "dubai_dld_areas.csv")
    else:
        print("  ⚠ No area data — will use reference from existing dubai_dld_areas.csv if present")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Transactions (Sales): {len(all_sales)}")
    if all_sales:
        print(f"  Price range (sample): {all_sales[0].get('TRANS_VALUE','N/A')}")

if __name__ == "__main__":
    main()