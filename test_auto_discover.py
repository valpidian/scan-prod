import sys
import os
from pathlib import Path

# Add the project root to the path
project_root = r"D:\CODEX\scan-pret"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set up Flask app context
from app import create_app

app = create_app()
with app.app_context():
    from app.services.web_scraping_service import auto_discover_selectors, _METADATA_PROPERTIES
    import json
    from pprint import pprint
    
    # 1. Print _METADATA_PROPERTIES to verify it exists and has data
    print("=" * 80)
    print("_METADATA_PROPERTIES:")
    print("=" * 80)
    pprint(_METADATA_PROPERTIES)
    print()
    
    # 2. Call auto_discover_selectors with the provided URL
    test_url = "https://www.climatico.ro/aer-conditionat-whirlpool-amd-355-1-inverter-premium-sail-silver-12000-btu.html"
    print("=" * 80)
    print(f"Calling auto_discover_selectors for: {test_url}")
    print("=" * 80)
    
    result = auto_discover_selectors(test_url)
    
    # 3. Pretty-print the complete result
    print("\nComplete Result:")
    print("-" * 80)
    pprint(result)
    print()
    
    # 4. For each field, print source, value, selector if found
    print("=" * 80)
    print("Detailed Field Analysis:")
    print("=" * 80)
    
    if result and isinstance(result, dict):
        for field, data in result.items():
            print(f"\nField: {field}")
            print(f"  Type: {type(data)}")
            if isinstance(data, dict):
                for key in ['source', 'value', 'selector']:
                    if key in data:
                        print(f"  {key}: {data[key]}")
                # Show any other keys
                other_keys = set(data.keys()) - {'source', 'value', 'selector'}
                for key in other_keys:
                    print(f"  {key}: {data[key]}")
            else:
                print(f"  value: {data}")
    else:
        print(f"Result is: {result}")
