#!/usr/bin/env python
import sys
import os
sys.path.insert(0, os.getcwd())

from app import create_app

app = create_app()
with app.app_context():
    from bs4 import BeautifulSoup
    from app.services.web_scraping_service import _get, _METADATA_PROPERTIES, _CSS_HINTS
    from price_parser import Price
    
    url = "https://www.climatico.ro/aer-conditionat-whirlpool-amd-355-1-inverter-premium-sail-silver-12000-btu.html"
    
    try:
        resp = _get(url, timeout=15)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        print(f"ERROR fetching: {exc}")
        sys.exit(1)
    
    print("="*70)
    print(f"Testing auto_discover logic for: {url}")
    print("="*70)
    
    # First, verify soup is working
    print(f"\nSoup type: {type(soup)}")
    print(f"HTML length: {len(html)}")
    
    # Test direct selector
    print("\n[DIRECT SELECTOR TEST]")
    direct_test = soup.select_one("meta[property='og:title']")
    print(f"Direct test meta[property='og:title']: {direct_test}")
    if direct_test:
        print(f"  content: {direct_test.get('content')}")
    
    # Test all meta tags
    all_metas = soup.find_all("meta", property=True)
    print(f"\nAll meta tags with property attribute: {len(all_metas)}")
    for i, m in enumerate(all_metas[:5]):
        print(f"  {i}: {m.get('property')} = {repr(m.get('content', '')[:50])}")
    
    # Test JUST the title field manually
    field = "title"
    print(f"\n[TESTING FIELD: {field}]")
    print(f"Field in _METADATA_PROPERTIES? {field in _METADATA_PROPERTIES}")
    
    if field in _METADATA_PROPERTIES:
        print(f"Metadata selectors for {field}: {_METADATA_PROPERTIES[field]}")
        
        for prop_name, meta_selector in _METADATA_PROPERTIES[field]:
            print(f"\n  Testing selector: {meta_selector}")
            try:
                meta_el = soup.select_one(meta_selector)
                print(f"    Element found? {meta_el is not None}")
                
                if meta_el:
                    content = meta_el.get("content", "").strip()
                    print(f"    Content: {repr(content)} (len={len(content)})")
                    
                    if content:
                        valid = True
                        if field == "title" and len(content) > 300:
                            valid = False
                        print(f"    Valid? {valid}")
                        
                        if valid:
                            print(f"    ✓ WOULD BE ADDED TO CANDIDATES")
                    else:
                        print(f"    Content empty after strip")
                else:
                    print(f"    Meta tag not found!")
            except Exception as e:
                print(f"    Exception: {e}")
                import traceback
                traceback.print_exc()
