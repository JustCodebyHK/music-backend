import main
import requests

print("Testing YouTube Music search (should not use proxy)...")
try:
    results = main.ytm.search("test", filter="songs")
    print(f"✓ Search succeeded! Got {len(results)} results")
except Exception as e:
    err = str(e)
    if "proxy" in err.lower():
        print(f"✗ Still proxy error: {err[:200]}")
    else:
        print(f"✗ Other error: {err[:200]}")
