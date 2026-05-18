import requests
from bs4 import BeautifulSoup
import sys

# URL to test
url = "https://www.climatico.ro/aer-conditionat-whirlpool-amd-355-1-inverter-premium-sail-silver-12000-btu.html"

# Meta properties from web_scraping_service.py
_METADATA_PROPERTIES = {
    "title": [
        ("og:title", "meta[property='og:title']"),
        ("product:title", "meta[property='product:title']"),
    ],
    "pret": [
        ("product:price:amount", "meta[property='product:price:amount']"),
        ("product:price:currency", "meta[property='product:price:currency']"),
    ],
    "sku": [
        ("product:retailer_item_id", "meta[property='product:retailer_item_id']"),
        ("product:item_id", "meta[property='product:item_id']"),
    ],
    "brand": [
        ("product:brand", "meta[property='product:brand']"),
    ],
    "descriere": [
        ("og:description", "meta[property='og:description']"),
        ("product:description", "meta[property='product:description']"),
    ],
    "categorie": [
        ("product:category", "meta[property='product:category']"),
    ],
}

# User agent header
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ro-RO,ro;q=0.9",
}

print(f"\n{'='*80}")
print(f"Testing URL: {url}")
print(f"{'='*80}\n")

try:
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    
    # Test each field and its selectors
    for field, selectors in _METADATA_PROPERTIES.items():
        print(f"\n[FIELD: {field}]")
        for prop_name, meta_selector in selectors:
            try:
                meta_el = soup.select_one(meta_selector)
                found = meta_el is not None
                content = ""
                content_len = 0
                
                if found:
                    content = meta_el.get("content", "")
                    content_len = len(content)
                
                print(f"  Selector: {meta_selector}")
                print(f"  Found: {found}")
                if found:
                    print(f"  Content (raw, repr): {repr(content)}")
                    print(f"  Length: {content_len}")
                print()
            except Exception as e:
                print(f"  Selector: {meta_selector}")
                print(f"  ERROR: {e}")
                print()

    # Also test the specific selectors requested
    print(f"\n{'='*80}")
    print("SPECIFIC SELECTOR TESTS (as requested)")
    print(f"{'='*80}\n")
    
    specific_selectors = [
        "meta[property='og:title']",
        "meta[property='product:price:amount']",
        "meta[property='og:description']",
        "meta[property='product:retailer_item_id']",
    ]
    
    for selector in specific_selectors:
        meta_el = soup.select_one(selector)
        found = meta_el is not None
        content = ""
        content_len = 0
        
        if found:
            content = meta_el.get("content", "")
            content_len = len(content)
        
        print(f"Selector: {selector}")
        print(f"Found: {found}")
        if found:
            print(f"Content (raw, repr): {repr(content)}")
            print(f"Length: {content_len}")
        print()

except Exception as e:
    print(f"ERROR fetching URL: {e}")
    sys.exit(1)
