import requests
from bs4 import BeautifulSoup

url = 'https://www.climatico.ro/aer-conditionat-whirlpool-amd-355-1-inverter-premium-sail-silver-12000-btu.html'

print('Fetching URL...')
print('=' * 80)
print(f'URL: {url}')
print('=' * 80)

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    print(f'Status code: {response.status_code}')
    print(f'Content length: {len(response.content)} bytes')
    print()
    
    # Create BeautifulSoup from HTML
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Test 1: Double quotes selector
    print('Test 1: soup.select_one("meta[property=\"og:title\"]")')
    print('-' * 80)
    result1 = soup.select_one('meta[property="og:title"]')
    print(f'Result: {result1}')
    print()
    
    # Test 2: Single quotes selector
    print("Test 2: soup.select_one('meta[property=\"og:title\"]')")
    print('-' * 80)
    result2 = soup.select_one("meta[property='og:title']")
    print(f'Result: {result2}')
    print()
    
    # Test 3: Manual search for all meta tags with property attribute
    print('Test 3: Manual search for all meta tags with property attribute')
    print('-' * 80)
    meta_tags_with_property = soup.find_all('meta', property=True)
    print(f'Total meta tags with property attribute: {len(meta_tags_with_property)}')
    print()
    
    # Show first 5 examples
    print('First 5 examples:')
    for i, tag in enumerate(meta_tags_with_property[:5]):
        print(f'{i+1}. {tag}')
    print()
    
    # Test 4: Show one meta[property] tag HTML exactly
    if meta_tags_with_property:
        print('Test 4: Exact HTML of first meta[property] tag')
        print('-' * 80)
        first_tag = meta_tags_with_property[0]
        print(f'Tag string: {str(first_tag)}')
        print(f'Tag name: {first_tag.name}')
        print(f'Tag attributes: {first_tag.attrs}')
        print()
        
        # Also check for og:title specifically
        og_title_tags = [tag for tag in meta_tags_with_property if tag.get('property') == 'og:title']
        if og_title_tags:
            print(f'Found og:title tag:')
            print(f'{og_title_tags[0]}')
        else:
            print('No og:title tag found in meta tags with property attribute')
    
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
