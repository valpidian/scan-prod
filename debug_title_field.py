import requests
from bs4 import BeautifulSoup
import sys
import json

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
print(f"STEP 1: Check if 'title' is in _METADATA_PROPERTIES")
print(f"{'='*80}")
is_title_in_metadata = "title" in _METADATA_PROPERTIES
print(f"Result: {is_title_in_metadata}")

print(f"\n{'='*80}")
print(f"STEP 2: Print _METADATA_PROPERTIES['title'] selectors")
print(f"{'='*80}")
title_selectors = _METADATA_PROPERTIES.get("title", [])
print(f"Selectors to test for 'title': {title_selectors}")

print(f"\n{'='*80}")
print(f"STEP 3: Load page and create BeautifulSoup")
print(f"{'='*80}")
try:
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    print(f"Page loaded successfully. Status code: {resp.status_code}")
    print(f"Content length: {len(resp.content)} bytes")
except Exception as e:
    print(f"ERROR fetching URL: {e}")
    sys.exit(1)

print(f"\n{'='*80}")
print(f"STEP 4: Manually test each selector for 'title' field")
print(f"{'='*80}\n")

# Manual testing logic for title field - simulating auto_discover_selectors
metadata_candidates = {
    "title": []
}

for prop_name, meta_selector in title_selectors:
    print(f"Testing selector: {meta_selector}")
    print(f"  Property name: {prop_name}")
    
    try:
        # This is the core logic from auto_discover_selectors
        meta_el = soup.select_one(meta_selector)
        found = meta_el is not None
        
        print(f"  soup.select_one() result: {found}")
        
        if found:
            content = meta_el.get("content", "")
            content_len = len(content)
            
            print(f"  Content (repr): {repr(content)}")
            print(f"  Content length: {content_len}")
            
            # Validation logic (checking if not empty)
            is_valid = content_len > 0
            print(f"  Is valid (non-empty): {is_valid}")
            
            if is_valid:
                # This is where it gets added to candidates
                metadata_candidates["title"].append({
                    "selector": meta_selector,
                    "value": content,
                    "prop_name": prop_name
                })
                print(f"  ✓ ADDED to metadata_candidates")
            else:
                print(f"  ✗ REJECTED (empty content)")
        else:
            print(f"  ✗ REJECTED (selector not found)")
    
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
    
    print()

print(f"{'='*80}")
print(f"STEP 5: Final metadata_candidates for 'title' field")
print(f"{'='*80}")
print(json.dumps(metadata_candidates, indent=2, ensure_ascii=False))

print(f"\n{'='*80}")
print(f"STEP 6: Now test auto_discover_selectors function (if available)")
print(f"{'='*80}")

# Try to import and run auto_discover_selectors if it exists
try:
    from web_scraping_service import auto_discover_selectors
    print("\nImported auto_discover_selectors from web_scraping_service")
    
    result = auto_discover_selectors(url)
    print("\nResult from auto_discover_selectors:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Compare with manual result
    print(f"\n{'='*80}")
    print(f"COMPARISON: Manual vs auto_discover_selectors")
    print(f"{'='*80}")
    print(f"\nManual 'title' candidates:")
    for item in metadata_candidates["title"]:
        print(f"  - {item['selector']}: {repr(item['value'][:50])}")
    
    print(f"\nAuto-discover 'title' candidates:")
    auto_title = result.get("title", {})
    if isinstance(auto_title, dict):
        for key, val in auto_title.items():
            print(f"  - {key}: {repr(str(val)[:50])}")
    else:
        print(f"  - Value: {repr(str(auto_title)[:50])}")
    
except ImportError as e:
    print(f"Could not import auto_discover_selectors: {e}")
    print("This is OK - the manual testing above shows the logic")
except Exception as e:
    print(f"Error running auto_discover_selectors: {e}")
    import traceback
    traceback.print_exc()
