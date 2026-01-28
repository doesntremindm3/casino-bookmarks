# Add this right after the host line in index()
import sys
host = request.headers.get('Host', '').lower()
print(f"DEBUG: Received host header: '{host}'", file=sys.stderr, flush=True)
if '.bookmarks.dougshipe.com' in host:
    before_split = host.split('.bookmarks.dougshipe.com')[0]
    print(f"DEBUG: Before final split: '{before_split}'", file=sys.stderr, flush=True)
    subdomain = before_split.split('.')[-1]
    print(f"DEBUG: Final subdomain: '{subdomain}'", file=sys.stderr, flush=True)
