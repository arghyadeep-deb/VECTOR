"""Test the absorbed module API endpoint."""
import ssl, urllib.request, json
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

try:
    r = urllib.request.urlopen("https://127.0.0.1:8765/absorbed/models", context=ctx, timeout=5)
    d = json.loads(r.read())
    print(f"Models: {d['count']}")
    for m in d["models"][:8]:
        print(f"  {m['id']:<30s} {m.get('provider',''):15s} {m.get('min_vram_gb',0)}GB")
except Exception as e:
    print(f"FAIL: {e}")

try:
    r = urllib.request.urlopen("https://127.0.0.1:8765/absorbed/connectors", context=ctx, timeout=5)
    d = json.loads(r.read())
    print(f"\nConnectors: {d['count']}")
    for c in d["connectors"][:8]:
        print(f"  {c}")
except Exception as e:
    print(f"Connectors FAIL: {e}")
